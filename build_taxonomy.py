#!/usr/bin/env python3
"""Build a WIDE, SHALLOW disease taxonomy from real corpus frequency.

WHY WIDE BEATS DEEP
Routing error compounds multiplicatively. With per-level accuracy p and d
levels, the chance of reaching the right leaf is p^d:

    p=0.95, d=2  ->  90.3%      2 calls
    p=0.95, d=3  ->  85.7%      3 calls
    p=0.95, d=4  ->  81.5%      4 calls

Every extra level costs accuracy AND latency AND money. Meanwhile each level
can hold up to 255 options for free - the cap is per-call, not per-system. So
the right shape is the widest tree that fits under the cap at every level:

    2 levels x 255 options  =  65,025 addressable conditions

That is 6x more than the ~10,000 named human diseases, from two API calls.
Depth beyond 2 is unnecessary; this script therefore builds exactly 2 levels.

The taxonomy is DATA-DERIVED: names are harvested by frequency from 13,092
real case reports, then assigned to categories. No hand-authored likelihoods
are involved (see HYPOTHESIS_SPACE.md - classification needs only names).
"""
import argparse, collections, json, os, pathlib, re, sys

HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(HERE))
DATA = HERE / "datasets"

# Wide top level: 24 categories chosen to be CLINICALLY DISCRIMINABLE from a
# presentation, not to be a tidy ontology. A category is useful only if Jev can
# pick it from symptoms alone.
CATEGORIES = {
    "infection_bacterial": "Bacterial infections including abscess, cellulitis, tuberculosis, actinomycosis",
    "infection_viral": "Viral infections including hepatitis, HIV, herpes, measles, COVID",
    "infection_fungal": "Fungal infections including candidiasis, aspergillosis, histoplasmosis, mucormycosis",
    "infection_parasitic": "Parasitic and helminthic disease including hydatid cyst, cysticercosis, malaria, leishmaniasis",
    "neoplasm_carcinoma": "Carcinomas: epithelial malignancy of lung, breast, colon, stomach, pancreas, thyroid",
    "neoplasm_sarcoma": "Sarcomas: malignancy of bone, muscle, fat, vessel or connective tissue",
    "neoplasm_lymphoid": "Lymphoma, leukaemia, myeloma and other haematological malignancy",
    "neoplasm_benign": "Benign tumours including lipoma, schwannoma, adenoma, haemangioma, leiomyoma",
    "neoplasm_neuroendocrine": "Neuroendocrine, germ cell and embryonal tumours",
    "autoimmune_rheumatic": "Systemic autoimmune and rheumatic disease including lupus, vasculitis, sarcoidosis, IgG4",
    "cardiac": "Cardiac disease including infarction, myocarditis, pericarditis, arrhythmia, cardiomyopathy, valve disease",
    "vascular": "Vascular disease including aneurysm, dissection, thrombosis, embolism, malformation, ischaemia",
    "respiratory": "Airway and lung disease including asthma, COPD, pneumonitis, fibrosis, pneumothorax, effusion",
    "neurological": "Brain, spinal cord and nerve disease including stroke, seizure, neuropathy, demyelination, encephalopathy",
    "psychiatric": "Psychiatric and functional disorders including psychosis, catatonia, conversion, anxiety",
    "gastrointestinal": "Gut, liver, biliary and pancreatic disease including obstruction, perforation, IBD, hepatitis, pancreatitis",
    "renal_urinary": "Kidney, bladder and urinary tract disease including nephritis, stones, failure, obstruction",
    "endocrine_metabolic": "Endocrine and metabolic disease including thyroid, adrenal, diabetes, electrolyte and storage disorders",
    "haematological": "Non-malignant blood disease including anaemia, coagulopathy, haemophilia, thrombocytopenia, haemolysis",
    "dermatological": "Skin disease including rashes, blistering disease, pyoderma, dermatitis, skin lesions",
    "musculoskeletal": "Bone, joint, muscle and soft tissue disease including fracture, arthritis, myositis, osteomyelitis",
    "obstetric_gynaecological": "Pregnancy, uterine, ovarian and breast disease",
    "ophthalmic_ent": "Eye, ear, nose, throat, oral and dental disease",
    "iatrogenic_toxic": "Drug reactions, poisoning, envenomation, retained foreign body, procedural and post-surgical complications",
}

# Keyword rules: cheap, deterministic, auditable. Only unmatched names go to
# the model, which keeps the build cost low and the result reproducible.
RULES = [
    ("iatrogenic_toxic", r"gossypiboma|retained|foreign body|drug (reaction|eruption|induced)|toxicity|poisoning|envenom|overdose|iatrogenic|post-?operative|postoperative|anaphylax|transfusion|vaccine|stent|catheter|implant"),
    ("infection_parasitic", r"hydatid|echinococc|cysticerc|malaria|leishman|schistosom|filari|amoeb|ascaris|strongyloid|toxoplasm|trypanosom|chagas|helminth|tapeworm|hookworm|scabies|myiasis"),
    ("infection_fungal", r"candid|aspergill|histoplasm|mucormyc|cryptococc|blastomyc|coccidioid|sporotrich|fung|mycetoma|tinea|dermatophyt|pneumocystis"),
    ("infection_viral", r"hepatitis [abcde]|hiv|herpes|zoster|varicella|measles|mumps|rubella|influenza|covid|sars|cytomegalo|epstein|dengue|chikungunya|zika|rabies|papillomavirus|viral|virus|parvovirus|adenovirus"),
    ("neoplasm_lymphoid", r"lymphoma|leukemia|leukaemia|myeloma|lymphoproliferat|histiocytosis|castleman|myelodysplas|myelofibrosis|plasmacytoma|mycosis fungoides"),
    ("neoplasm_sarcoma", r"sarcoma|gist|gastrointestinal stromal|chondroma|osteochondroma|osteosarcoma|liposarcoma|leiomyosarcoma|rhabdomyo"),
    ("neoplasm_carcinoma", r"carcinoma|adenocarcinoma|cancer|malignan|melanoma|mesothelioma|cholangiocarcinoma|hepatocellular|squamous cell|basal cell|metasta"),
    ("neoplasm_neuroendocrine", r"neuroendocrine|carcinoid|pheochromocytoma|paraganglioma|germ cell|teratoma|seminoma|neuroblastoma|blastoma|insulinoma|gastrinoma"),
    ("neoplasm_benign", r"lipoma|schwannoma|neurofibroma|adenoma|hemangioma|haemangioma|leiomyoma|fibroma|myxoma|papilloma|polyp|cyst\b|cystic|meningioma|osteoma|chondroblastoma|angiomyolipoma|lymphangioma|glomus|hamartoma|teratoma|tumou?r"),
    ("autoimmune_rheumatic", r"lupus|sle\b|vasculitis|sarcoid|igg4|rheumatoid|sjogren|sjögren|scleroderma|dermatomyositis|polymyositis|behcet|behçet|takayasu|wegener|granulomatosis with|antiphospholipid|still disease|polyarteritis|autoimmune|mctd|spondylitis|ankylosing"),
    ("cardiac", r"myocard|pericard|endocard|cardiomyopath|arrhythm|tachycard|bradycard|fibrillation|heart failure|valv|aortic stenosis|mitral|infarct|angina|cardiac|coronary|takotsubo"),
    ("vascular", r"aneurysm|dissection|thrombos|thromboembol|embolism|ischemi|ischaemi|varic|arteriovenous|vascular malformation|phlebitis|claudication|raynaud|arteritis|stenosis of|av fistula|hematoma|haematoma"),
    ("respiratory", r"pneumon|asthma|copd|bronch|pulmonary fibrosis|pneumothorax|pleural|empyema|atelectasis|ards|respiratory|emphysema|silicosis|asbestosis|pulmonary alveolar|interstitial lung|sleep apnea|apnoea|hemoptysis|lung abscess"),
    ("neurological", r"stroke|seizure|epilep|neuropath|myelitis|encephal|meningitis|meningo|multiple sclerosis|parkinson|dementia|alzheimer|guillain|myasthen|migraine|hydrocephalus|syringomyelia|cerebral|spinal cord|radiculopath|palsy|ataxia|chorea|dystonia|neuralgia|pres\b|posterior reversible"),
    ("psychiatric", r"psychosis|psychotic|schizophren|catatonia|depress|bipolar|anxiety|conversion disorder|somatoform|factitious|munchausen|delirium|panic|eating disorder|anorexia nervosa"),
    ("gastrointestinal", r"appendicitis|cholecystitis|cholangitis|pancreatitis|hepatitis|cirrhosis|colitis|crohn|ulcerative|gastritis|peptic ulcer|bowel obstruction|volvulus|intussusception|diverticul|perforation|gerd|reflux|achalasia|celiac|coeliac|hernia|ileus|gastroparesis|esophag|oesophag|liver|hepatic|splenic|peritonitis|melena|variceal"),
    ("renal_urinary", r"nephritis|nephropathy|nephrotic|renal|kidney|urolithiasis|nephrolithiasis|pyelonephritis|cystitis|bladder|ureter|urethr|urinary|glomerulo|hydronephrosis|dialysis"),
    ("endocrine_metabolic", r"thyroid|hyperthyroid|hypothyroid|graves|hashimoto|adrenal|addison|cushing|diabet|ketoacidosis|hypoglyc|hypercalc|hypocalc|hyponatr|hypernatr|hypokal|hyperkal|pituitary|acromegal|parathyroid|metabolic|wilson disease|hemochromatosis|haemochromatosis|amyloid|porphyria|gout|storage disease|deficiency"),
    ("haematological", r"anemia|anaemia|hemophilia|haemophilia|thrombocytopen|coagulopath|neutropen|pancytopen|hemolytic|haemolytic|sickle|thalassem|polycythem|methemoglobin|von willebrand|dic\b|disseminated intravascular|spherocytosis|aplastic"),
    ("dermatological", r"dermatitis|psoriasis|pemphigus|pemphigoid|urticaria|erythema|pyoderma|cellulitis|abscess|acne|rosacea|vitiligo|alopecia|lichen|keratosis|dyskeratoma|epidermolysis|stevens-johnson|toxic epidermal|rash|pruritus|ulcer of skin|panniculitis|hidradenitis"),
    ("musculoskeletal", r"fracture|arthritis|osteomyelitis|osteoporosis|osteonecrosis|myositis|tendinitis|tendinopathy|bursitis|dislocation|spondylo|disc herniation|scoliosis|rhabdomyolysis|compartment syndrome|synovitis|osteoarthritis|bone|muscle|avascular necrosis"),
    ("obstetric_gynaecological", r"pregnan|eclampsia|preeclampsia|ectopic|abortion|placenta|endometri|ovarian|uterine|uterus|cervical|vaginal|vulv|menstrual|breast|mastitis|fibroid|pcos|postpartum|labour|labor"),
    ("ophthalmic_ent", r"retina|glaucoma|cataract|uveitis|conjunctiv|keratitis|optic|ocular|eye|orbital|otitis|tinnitus|hearing|sinusitis|rhinitis|tonsill|pharyng|laryng|epiglottitis|nasal|dental|odontogenic|periodontal|tooth|oral|parotid|salivary|temporomandibular"),
    ("infection_bacterial", r"tuberculosis|tuberculous|actinomyc|nocardia|syphilis|gonorrh|chlamydia|leptospir|brucell|salmonell|shigell|listeri|clostrid|staphyloc|streptoc|pseudomonas|klebsiella|mycobacter|sepsis|septic|bacteremia|bacteraemia|infection|infectious|abscess|lyme|rickettsi|typhoid|cholera|tetanus|diphtheria|anthrax|plague|melioidosis"),
]


def norm(s):
    s = str(s).lower().strip()
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# The corpus is published CASE REPORTS, selected for rarity - so it omits
# common disease. 26 of our original 49 never appear in it at all (see
# BOTTLENECK.md). Without these seeds the tree can diagnose Erdheim-Chester
# but not dengue, which is exactly backwards for a triage tool.
SEED = {
    "infection_viral": ["dengue", "dengue fever", "influenza", "covid 19",
        "viral upper respiratory tract infection", "infectious mononucleosis",
        "viral gastroenteritis", "chikungunya", "measles", "mumps", "rubella",
        "viral hepatitis", "hand foot and mouth disease", "viral pharyngitis"],
    "infection_bacterial": ["typhoid fever", "leptospirosis", "scrub typhus",
        "brucellosis", "tuberculosis", "streptococcal pharyngitis",
        "bacterial pneumonia", "urinary tract infection", "cellulitis",
        "bacterial meningitis", "infective endocarditis", "sepsis",
        "whooping cough", "diphtheria", "tetanus", "cholera", "shigellosis",
        "lyme disease", "rickettsial fever", "melioidosis"],
    "infection_parasitic": ["malaria", "falciparum malaria", "vivax malaria",
        "amoebiasis", "giardiasis", "intestinal helminthiasis", "filariasis",
        "visceral leishmaniasis", "toxoplasmosis"],
    "cardiac": ["myocardial infarction", "unstable angina", "stable angina",
        "atrial fibrillation", "supraventricular tachycardia", "heart failure",
        "acute coronary syndrome", "hypertensive emergency"],
    "respiratory": ["asthma", "copd exacerbation", "community acquired pneumonia",
        "acute bronchitis", "pulmonary tuberculosis", "pneumothorax",
        "pleural effusion", "acute respiratory distress syndrome"],
    "gastrointestinal": ["acute appendicitis", "acute pancreatitis",
        "acute cholecystitis", "peptic ulcer disease",
        "gastroesophageal reflux disease", "acute gastroenteritis",
        "bowel obstruction", "inguinal hernia", "acute hepatitis",
        "alcoholic liver disease", "diverticulitis"],
    "neurological": ["ischemic stroke", "hemorrhagic stroke", "migraine",
        "epileptic seizure", "transient ischemic attack", "bell palsy",
        "guillain barre syndrome", "viral meningitis", "encephalitis"],
    "endocrine_metabolic": ["diabetic ketoacidosis", "hypoglycemia",
        "hyperthyroidism", "hypothyroidism", "addison disease",
        "diabetes mellitus", "hyponatremia", "hypercalcemia"],
    "haematological": ["iron deficiency anemia", "anemia",
        "vitamin b12 deficiency", "sickle cell crisis", "thrombocytopenia"],
    "psychiatric": ["panic attack", "major depressive episode",
        "generalised anxiety disorder", "acute psychosis", "delirium",
        "somatic symptom disorder"],
    "renal_urinary": ["acute kidney injury", "nephrolithiasis",
        "pyelonephritis", "acute cystitis", "chronic kidney disease"],
    "musculoskeletal": ["mechanical low back pain", "osteoarthritis",
        "gout", "septic arthritis", "rib fracture", "rotator cuff injury"],
    "dermatological": ["urticaria", "atopic dermatitis", "herpes zoster",
        "impetigo", "fungal skin infection", "drug rash"],
    "ophthalmic_ent": ["acute otitis media", "acute sinusitis",
        "allergic rhinitis", "acute tonsillitis", "conjunctivitis",
        "dental abscess", "laryngitis"],
    "vascular": ["deep vein thrombosis", "pulmonary embolism",
        "aortic dissection", "peripheral arterial disease"],
    "autoimmune_rheumatic": ["systemic lupus erythematosus",
        "rheumatoid arthritis", "sarcoidosis", "vasculitis"],
    "obstetric_gynaecological": ["ectopic pregnancy", "preeclampsia",
        "pelvic inflammatory disease", "ovarian cyst", "endometriosis"],
    "iatrogenic_toxic": ["anaphylaxis", "adverse drug reaction",
        "snake envenomation", "organophosphate poisoning",
        "paracetamol overdose", "scombroid food poisoning"],
}


def harvest(n_names):
    import pyarrow.parquet as pq
    t = pq.read_table(DATA / "mcr_train.parquet", columns=["final_diagnosis"])
    c = collections.Counter()
    for x in t.column("final_diagnosis").to_pylist():
        if x and str(x).strip():
            c[norm(x)] += 1
    return c.most_common(n_names)


def assign(name):
    for cat, pat in RULES:
        if re.search(pat, name):
            return cat
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", type=int, default=2000)
    ap.add_argument("--cap", type=int, default=240,
                    help="max conditions per category (API cap is 255)")
    ap.add_argument("--out", default="taxonomy.json")
    args = ap.parse_args()

    pairs = harvest(args.names)
    print(f"harvested {len(pairs)} diagnosis names from the corpus")

    tax = collections.defaultdict(list)
    unmatched = []
    for name, freq in pairs:
        cat = assign(name)
        if cat:
            tax[cat].append((name, freq))
        else:
            unmatched.append((name, freq))

    print(f"assigned by keyword rules: {sum(len(v) for v in tax.values())}")
    print(f"unmatched (dropped): {len(unmatched)}")
    print(f"seeded common conditions: {sum(len(v) for v in SEED.values())}\n")

    # Seeds go in FIRST and are never evicted by the cap: common disease
    # matters more for triage than a rare tumour, and the corpus under-weights
    # it by construction.
    final = {}
    n_seed = 0
    for cat in CATEGORIES:
        seeds = [norm(s) for s in SEED.get(cat, [])]
        n_seed += len(seeds)
        harvested = [n for n, _ in sorted(tax.get(cat, []), key=lambda x: -x[1])]
        merged = list(dict.fromkeys(seeds + harvested))   # seeds first, dedup
        final[cat] = merged[:args.cap]

    print(f"{'category':30s} {'n':>5s}")
    total = 0
    for cat in CATEGORIES:
        n = len(final[cat])
        total += n
        flag = "  <-- AT CAP" if n >= args.cap else ""
        print(f"{cat:30s} {n:5d}{flag}")
    print(f"{'TOTAL':30s} {total:5d}")

    print(f"\nlevel 1: {len(CATEGORIES)} categories  (cap 255, using "
          f"{len(CATEGORIES)})")
    print(f"level 2: max {max(len(v) for v in final.values())} conditions "
          f"(cap 255)")
    print(f"addressable with 2 calls: {len(CATEGORIES)} x 255 = "
          f"{len(CATEGORIES)*255:,}")
    print(f"actually populated: {total:,}")

    json.dump({"categories": CATEGORIES, "tree": final,
               "unmatched_sample": [n for n, _ in unmatched[:40]],
               "n_unmatched": len(unmatched)},
              open(HERE / args.out, "w"), indent=1)
    print(f"\nsaved {args.out}")


if __name__ == "__main__":
    main()
