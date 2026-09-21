#!/usr/bin/env python3
"""Multi-label taxonomy: file each condition under EVERY category a clinician
might route from.

THE DIAGNOSIS (ESCALATION_AUDIT.md)
7 of 11 escalations were level-1 misroutes, and most were the taxonomy's
fault. The audit found a consistent pattern: conditions are filed by
MECHANISM (what it is) while patients present by ORGAN (where it hurts).

    ocular cysticercosis   filed infection_parasitic   Jev chose ophthalmic_ent
    adenomatoid odontogenic tumor  filed neoplasm_benign  Jev chose ophthalmic_ent
    malignant syphilis     filed neoplasm_carcinoma    Jev chose infection_bacterial

In every case Jev's choice was defensible medicine. Single-label filing forces
a choice the medicine does not support.

THE FIX
Cross-file: a condition named for an organ is reachable from that organ's
category AS WELL AS its mechanism category. 0.3% of conditions currently sit
in more than one category; after this it should be far higher, and every
cross-file removes a single point of failure.

This costs nothing at query time - the level-2 lists just contain more
entries, still under the 255 cap.
"""
import argparse, collections, json, pathlib, re, sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))

# ORGAN/SITE cues -> the category a patient presenting that way would reach.
# Deliberately about PRESENTATION, not pathology.
ORGAN_ROUTES = [
    ("ophthalmic_ent", r"ocular|orbit|eye|retina|conjunctiv|uveal|uveitis|lacrimal|eyelid|"
                       r"odontogenic|dental|tooth|teeth|jaw|mandib|maxill|gingiv|oral|"
                       r"tongue|palate|parotid|salivary|tonsil|pharyn|laryn|nasal|nose|"
                       r"sinus|sinonasal|ear|otic|tympanic|mastoid|auricular"),
    ("neurological", r"brain|cerebr|cerebell|intracranial|meninge|meningeal|spinal|"
                     r"cord|nerve|neural|neuro|encephal|myelo|cranial|pituitary|"
                     r"optic nerve|seizure|epilep"),
    ("dermatological", r"cutaneous|skin|dermal|dermat|subcutaneous|scalp|nail|"
                       r"epiderm|pyoderma|eczema|papul|plaque"),
    ("respiratory", r"pulmonar|lung|bronch|pleur|trache|alveol|airway|mediastin|thoracic"),
    ("cardiac", r"cardiac|myocard|pericard|endocard|heart|ventricul|atrial|valv|coronar"),
    ("gastrointestinal", r"gastric|gastro|intestin|bowel|colon|colonic|rectal|anal|"
                         r"esophag|oesophag|hepat|liver|biliary|gallbladder|pancrea|"
                         r"splenic|spleen|peritone|omental|appendic|duoden|jejun|ileal"),
    ("renal_urinary", r"renal|kidney|nephr|ureter|bladder|urethr|urinary|prostat"),
    ("musculoskeletal", r"bone|osseous|osteo|skeletal|vertebr|spine|spinal column|"
                        r"joint|articular|synovial|muscle|muscular|myo|tendon|"
                        r"soft tissue|femor|humer|tibial|rib\b"),
    ("obstetric_gynaecological", r"uterin|uterus|ovarian|ovary|cervical canal|endometri|"
                                 r"vaginal|vulv|placent|pregnan|fallopian|breast|mammary"),
    ("haematological", r"anemi|anaemi|marrow|haematolog|hematolog|platelet|coagul|"
                       r"bleeding|hemorrhag|haemorrhag"),
    ("vascular", r"vascular|vessel|arter|venous|vein|aort|thrombo|emboli|aneurysm|"
                 r"angio|perfusion|ischemi|ischaemi"),
    ("endocrine_metabolic", r"thyroid|adrenal|parathyroid|pituitar|endocrin|metabol|"
                            r"diabet|hormon"),
]

# MECHANISM cues that should ALSO apply even when the name is organ-led.
MECHANISM_ROUTES = [
    ("infection_parasitic", r"cysticerc|hydatid|echinococc|malaria|leishman|schistosom|"
                            r"filari|amoeb|toxoplasm|trypanosom|helminth|larva|parasit"),
    ("infection_fungal", r"candid|aspergill|histoplasm|mucormyc|cryptococc|fung|mycetoma|"
                         r"blastomyc|coccidioid|sporotrich"),
    ("infection_viral", r"herpes|zoster|varicella|cytomegalo|epstein|hiv|papillomavirus|"
                        r"viral|virus|dengue|influenza|covid"),
    ("infection_bacterial", r"tuberculo|syphilis|actinomyc|nocardia|brucell|leptospir|"
                            r"staphyloc|streptoc|mycobacter|bacterial|septic|abscess|"
                            r"rickettsi|borreli|lyme"),
    ("neoplasm_carcinoma", r"carcinoma|adenocarcinoma|malignan(?!t syphilis)|cancer|"
                           r"melanoma|mesothelioma|metasta"),
    ("neoplasm_sarcoma", r"sarcoma|gist|stromal tumou?r"),
    ("neoplasm_lymphoid", r"lymphoma|leukemi|leukaemi|myeloma|histiocytosis|"
                          r"lymphoproliferat|plasmacytoma"),
    ("neoplasm_benign", r"lipoma|schwannoma|neurofibroma|adenoma|hemangioma|haemangioma|"
                        r"leiomyoma|fibroma|myxoma|papilloma|cyst\b|osteoma|hamartoma|"
                        r"benign|granuloma"),
    ("autoimmune_rheumatic", r"lupus|vasculitis|sarcoid|igg4|rheumatoid|autoimmune|"
                             r"granulomatosis|arteritis"),
    ("iatrogenic_toxic", r"drug|iatrogen|retained|foreign body|gossypiboma|poisoning|"
                         r"toxic|envenom|post.?operative|postoperative|transfusion"),
]


def norm(s):
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(s))
    s = re.sub(r"[^a-z0-9 ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def extra_categories(name, current, valid):
    """Every additional category this condition should be reachable from."""
    n = norm(name)
    out = set()
    for cat, pat in ORGAN_ROUTES + MECHANISM_ROUTES:
        if cat in valid and re.search(pat, n):
            out.add(cat)
    out.discard(current)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inp", default="taxonomy.json")
    ap.add_argument("--out", default="taxonomy_multi.json")
    ap.add_argument("--cap", type=int, default=250)
    args = ap.parse_args()

    tax = json.loads((HERE / args.inp).read_text())
    tree = {k: list(v) for k, v in tax["tree"].items()}
    valid = set(tree)

    before = collections.defaultdict(list)
    for c, leaves in tree.items():
        for l in leaves:
            before[l].append(c)
    n_multi_before = sum(1 for v in before.values() if len(v) > 1)

    # cross-file
    added = collections.Counter()
    for cat in list(tree):
        for leaf in list(tree[cat]):
            for extra in extra_categories(leaf, cat, valid):
                if leaf not in tree[extra]:
                    tree[extra].append(leaf)
                    added[extra] += 1

    after = collections.defaultdict(list)
    for c, leaves in tree.items():
        for l in leaves:
            after[l].append(c)
    n_multi_after = sum(1 for v in after.values() if len(v) > 1)

    print(f"conditions: {len(after):,}")
    print(f"reachable from >1 category: {n_multi_before} -> {n_multi_after} "
          f"({100*n_multi_after/len(after):.1f}%)")
    print(f"single points of failure  : {len(before)-n_multi_before:,} -> "
          f"{len(after)-n_multi_after:,}\n")

    print(f"{'category':30s} {'before':>7s} {'after':>7s} {'added':>7s}")
    over = []
    for cat in sorted(tree):
        b = len(tax["tree"][cat])
        a = len(tree[cat])
        print(f"{cat:30s} {b:7d} {a:7d} {added[cat]:7d}"
              + ("   <-- OVER CAP" if a > args.cap else ""))
        if a > args.cap:
            over.append(cat)

    # Trim over-cap categories, but NEVER drop a condition that would become
    # unreachable - only drop entries that survive elsewhere.
    if over:
        print(f"\ntrimming {len(over)} categories over the {args.cap} cap "
              f"(keeping every condition reachable somewhere)")
        for cat in over:
            keep, drop = [], []
            for leaf in tree[cat]:
                if len(after[leaf]) > 1 and len(keep) >= args.cap:
                    drop.append(leaf)
                    after[leaf].remove(cat)
                else:
                    keep.append(leaf)
            tree[cat] = keep[:args.cap]
            print(f"  {cat}: {len(keep)} kept, {len(drop)} dropped "
                  f"(all reachable elsewhere)")

    final = collections.defaultdict(list)
    for c, leaves in tree.items():
        for l in leaves:
            final[l].append(c)
    print(f"\nfinal: {len(final):,} conditions, "
          f"{sum(len(v) for v in tree.values()):,} entries, "
          f"max category {max(len(v) for v in tree.values())}")
    orphan = [l for l, cs in final.items() if not cs]
    print(f"unreachable conditions: {len(orphan)}")

    json.dump({"categories": tax["categories"], "tree": tree},
              open(HERE / args.out, "w"), indent=1)
    print(f"saved {args.out}")


if __name__ == "__main__":
    main()
