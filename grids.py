#!/usr/bin/env python3
"""Diagnostic grids: (syndrome, mechanism) -> conditions.

A grid is a LOOKUP, not a partition. A condition may legitimately appear in
several cells, because real differentials overlap: pulmonary embolism belongs
in the chest-pain differential AND the breathlessness differential, and a
clinician considers it from either entry point. Duplication across cells is
correct and intentional; validate_grids.py checks coverage, not uniqueness.

Two grids:
  TROPICAL  the original hand-authored tropical febrile illness grid
  DDXPLUS   all 49 DDXPlus pathologies, for evaluation against that dataset

Condition keys in DDXPLUS are the EXACT DDXPlus pathology strings, so scoring
is a string comparison with no normalisation and no fuzzy matching.
"""

# ---------------------------------------------------------------- syndromes
SYNDROMES = {
    "acute_febrile_undifferentiated":
        "Acute fever with no clear localising focus",
    "acute_respiratory":
        "Cough, breathlessness or wheeze predominate",
    "ent_upper_airway":
        "Ear, nose, sinus or throat symptoms predominate",
    "chest_pain":
        "Chest pain is the dominant problem",
    "cardiovascular":
        "Palpitations, syncope, or swelling of the legs predominate",
    "acute_abdominal":
        "Abdominal pain, heartburn, vomiting or a lump predominate",
    "acute_neurological":
        "Headache, weakness, abnormal movements or altered consciousness predominate",
    "haematological":
        "Pallor, fatigue from anaemia, bleeding or lymph node enlargement predominate",
    "musculoskeletal":
        "Joint, muscle or bone pain predominates",
    "skin_soft_tissue":
        "Rash, flushing, itching or localised swelling predominate",
    "allergic_reaction":
        "An acute allergic or hypersensitivity reaction predominates",
    "psychiatric_functional":
        "Anxiety, panic or another functional disorder predominates",
    "constitutional_chronic":
        "Long-standing weight loss, night sweats or fatigue predominate",
    "acute_diarrhoeal":
        "Diarrhoea is the dominant problem",
    "jaundice_hepatic":
        "Jaundice or liver dysfunction predominates",
    "urogenital":
        "Urinary or genital symptoms predominate",
}

# ------------------------------------------------- mechanisms (surgical sieve)
SIEVE = {
    "infective": "Caused by an infection",
    "autoimmune_inflammatory": "An autoimmune or inflammatory process",
    "neoplastic": "A cancer or blood malignancy",
    "vascular": "Blocked, burst or inflamed blood vessels, a clot, or heart muscle starved of blood",
    "arrhythmic_electrical": "An abnormal heart rhythm or electrical conduction problem",
    "allergic_hypersensitivity": "An allergic or hypersensitivity reaction",
    "metabolic_endocrine": "A metabolic, hormonal or electrolyte disturbance",
    "deficiency_nutritional": "A nutritional deficiency or blood-loss related deficiency",
    "toxic_drug": "A drug reaction, poisoning or toxin",
    "structural_surgical": "An obstruction, perforation, rupture, fracture or other structural problem",
    "degenerative_functional": "A degenerative, chronic-functional or reflex disorder",
    "psychological_functional": "A psychological or functional disorder",
}


# =============================================================== TROPICAL grid
TROPICAL = {
    ("acute_febrile_undifferentiated", "infective"): {
        "dengue": {"label": "Dengue fever", "incubation": (4, 10)},
        "malaria": {"label": "Malaria", "incubation": (7, 30)},
        "typhoid": {"label": "Enteric fever (typhoid)", "incubation": (6, 30)},
        "leptospirosis": {"label": "Leptospirosis", "incubation": (2, 30)},
        "scrub_typhus": {"label": "Scrub typhus", "incubation": (6, 21)},
        "influenza": {"label": "Influenza", "incubation": (1, 4)},
        "chikungunya": {"label": "Chikungunya", "incubation": (2, 12)},
        "covid19": {"label": "COVID-19", "incubation": (2, 14)},
        "brucellosis": {"label": "Brucellosis", "incubation": (5, 60)},
        "q_fever": {"label": "Q fever", "incubation": (14, 39)},
        "murine_typhus": {"label": "Murine typhus", "incubation": (6, 14)},
        "visceral_leishmaniasis": {"label": "Visceral leishmaniasis (kala-azar)",
                                   "incubation": (60, 180)},
        "melioidosis": {"label": "Melioidosis", "incubation": (1, 21)},
        "ebv_mono": {"label": "EBV infectious mononucleosis", "incubation": (30, 50)},
        "hiv_seroconversion": {"label": "Acute HIV seroconversion", "incubation": (14, 28)},
        "tuberculosis": {"label": "Tuberculosis", "incubation": (30, 3650)},
        "hepatitis_a": {"label": "Acute hepatitis A", "incubation": (15, 50)},
        "amoebic_liver_abscess": {"label": "Amoebic liver abscess", "incubation": (14, 150)},
    },
    ("acute_febrile_undifferentiated", "autoimmune_inflammatory"): {
        "sle_flare": {"label": "Systemic lupus erythematosus flare"},
        "stills_disease": {"label": "Adult-onset Still's disease"},
        "vasculitis": {"label": "Systemic vasculitis"},
        "rheumatic_fever": {"label": "Acute rheumatic fever"},
        "sarcoidosis": {"label": "Sarcoidosis"},
        "kawasaki": {"label": "Kawasaki disease"},
        "haemophagocytic": {"label": "Haemophagocytic lymphohistiocytosis"},
    },
    ("acute_febrile_undifferentiated", "neoplastic"): {
        "lymphoma_fever": {"label": "Lymphoma presenting as fever"},
        "leukaemia_fever": {"label": "Acute leukaemia presenting as fever"},
        "solid_tumour_fever": {"label": "Solid tumour with paraneoplastic fever"},
    },
    ("acute_febrile_undifferentiated", "toxic_drug"): {
        "drug_fever": {"label": "Drug fever"},
        "serotonin_syndrome": {"label": "Serotonin syndrome"},
        "neuroleptic_malignant": {"label": "Neuroleptic malignant syndrome"},
        "heat_stroke": {"label": "Heat stroke"},
    },
    ("acute_febrile_undifferentiated", "metabolic_endocrine"): {
        "thyroid_storm": {"label": "Thyroid storm"},
        "adrenal_crisis": {"label": "Adrenal crisis"},
    },
    ("acute_febrile_undifferentiated", "structural_surgical"): {
        "appendicitis": {"label": "Acute appendicitis"},
        "cholangitis": {"label": "Acute cholangitis"},
        "liver_abscess_pyogenic": {"label": "Pyogenic liver abscess"},
        "deep_abscess": {"label": "Deep-seated abscess"},
        "endocarditis": {"label": "Infective endocarditis"},
    },
    ("acute_respiratory", "infective"): {
        "influenza": {"label": "Influenza", "incubation": (1, 4)},
        "covid19": {"label": "COVID-19", "incubation": (2, 14)},
        "bacterial_pneumonia": {"label": "Community-acquired bacterial pneumonia"},
        "tuberculosis": {"label": "Tuberculosis", "incubation": (30, 3650)},
        "mycoplasma": {"label": "Mycoplasma pneumonia"},
        "legionella": {"label": "Legionnaires disease", "incubation": (2, 10)},
        "pertussis": {"label": "Pertussis"},
    },
    ("acute_abdominal", "structural_surgical"): {
        "appendicitis": {"label": "Acute appendicitis"},
        "cholecystitis": {"label": "Acute cholecystitis"},
        "perforation": {"label": "Perforated viscus"},
        "obstruction": {"label": "Intestinal obstruction"},
        "diverticulitis": {"label": "Diverticulitis"},
    },
    ("musculoskeletal", "autoimmune_inflammatory"): {
        "sle_flare": {"label": "Systemic lupus erythematosus flare"},
        "rheumatoid_arthritis": {"label": "Rheumatoid arthritis"},
        "stills_disease": {"label": "Adult-onset Still's disease"},
        "vasculitis": {"label": "Systemic vasculitis"},
        "reactive_arthritis": {"label": "Reactive arthritis"},
        "psoriatic_arthritis": {"label": "Psoriatic arthritis"},
        "polymyalgia": {"label": "Polymyalgia rheumatica"},
        "gout_pseudogout": {"label": "Gout or pseudogout"},
        "dermatomyositis": {"label": "Dermatomyositis"},
    },
    ("musculoskeletal", "infective"): {
        "septic_arthritis": {"label": "Septic arthritis"},
        "osteomyelitis": {"label": "Osteomyelitis"},
        "chikungunya": {"label": "Chikungunya arthritis", "incubation": (2, 12)},
        "rheumatic_fever": {"label": "Acute rheumatic fever"},
        "tb_spine": {"label": "Spinal tuberculosis"},
    },
    ("constitutional_chronic", "autoimmune_inflammatory"): {
        "sle_flare": {"label": "Systemic lupus erythematosus flare"},
        "sarcoidosis": {"label": "Sarcoidosis"},
        "vasculitis": {"label": "Systemic vasculitis"},
        "ibd": {"label": "Inflammatory bowel disease"},
    },
    ("constitutional_chronic", "neoplastic"): {
        "lymphoma": {"label": "Lymphoma"},
        "leukaemia": {"label": "Leukaemia"},
        "solid_tumour": {"label": "Occult solid tumour"},
        "myeloma": {"label": "Multiple myeloma"},
    },
    ("constitutional_chronic", "infective"): {
        "tuberculosis": {"label": "Tuberculosis", "incubation": (30, 3650)},
        "hiv_chronic": {"label": "Chronic HIV infection"},
        "brucellosis": {"label": "Brucellosis", "incubation": (5, 60)},
        "visceral_leishmaniasis": {"label": "Visceral leishmaniasis", "incubation": (60, 180)},
        "endocarditis": {"label": "Subacute infective endocarditis"},
    },
    ("acute_neurological", "infective"): {
        "bacterial_meningitis": {"label": "Bacterial meningitis"},
        "viral_meningitis": {"label": "Viral meningitis"},
        "cerebral_malaria": {"label": "Cerebral malaria"},
        "japanese_encephalitis": {"label": "Japanese encephalitis"},
        "hsv_encephalitis": {"label": "HSV encephalitis"},
        "tuberculous_meningitis": {"label": "Tuberculous meningitis"},
    },
}


# ================================================================ DDXPLUS grid
# Keys are the EXACT DDXPlus pathology strings so scoring needs no
# normalisation. Conditions appear in every cell where a clinician would
# genuinely consider them from that entry point.
def _c(label, **kw):
    d = {"label": label}
    d.update(kw)
    return d


DDXPLUS = {
    # ---- acute respiratory ------------------------------------------------
    ("acute_respiratory", "infective"): {
        "Pneumonia": _c("Pneumonia"),
        "Bronchitis": _c("Bronchitis - infection of the larger airways, productive cough, no consolidation"),
        "Bronchiolitis": _c("Bronchiolitis - small-airway infection, typically infants and young children"),
        "URTI": _c("Upper respiratory tract infection (common cold)"),
        "Influenza": _c("Influenza", incubation=(1, 4)),
        "Acute COPD exacerbation / infection": _c("Acute COPD exacerbation or infection, in a known smoker or COPD patient"),
        "Tuberculosis": _c("Tuberculosis", incubation=(30, 3650)),
        "Whooping cough": _c("Whooping cough (pertussis) - paroxysmal cough with whoop or vomiting"),
        "Croup": _c("Croup - barking cough and stridor in a young child"),
        "Acute laryngitis": _c("Acute laryngitis - hoarse or lost voice"),
        "Viral pharyngitis": _c("Viral pharyngitis - sore throat"),
        "Epiglottitis": _c("Epiglottitis - severe sore throat, drooling, muffled voice"),
        "Bronchiectasis": _c("Bronchiectasis - chronic daily purulent sputum"),
        "Acute rhinosinusitis": _c("Acute rhinosinusitis - blocked nose and facial pain with post-nasal drip causing cough"),
        "Chronic rhinosinusitis": _c("Chronic rhinosinusitis - nasal blockage over 12 weeks with post-nasal drip"),
        "Acute otitis media": _c("Acute otitis media - ear pain, often with a preceding cold"),
    },
    ("acute_respiratory", "allergic_hypersensitivity"): {
        "Bronchospasm / acute asthma exacerbation": _c("Bronchospasm or acute asthma exacerbation"),
        "Anaphylaxis": _c("Anaphylaxis - rapid airway swelling with collapse after an allergen"),
        "Allergic sinusitis": _c("Allergic sinusitis with post-nasal drip causing cough"),
    },
    ("acute_respiratory", "vascular"): {
        "Pulmonary embolism": _c("Pulmonary embolism - clot in the lung arteries"),
        "Acute pulmonary edema": _c("Acute pulmonary edema - fluid in the lungs from heart failure"),
    },
    ("acute_respiratory", "structural_surgical"): {
        "Spontaneous pneumothorax": _c("Spontaneous pneumothorax - collapsed lung"),
        "Bronchiectasis": _c("Bronchiectasis - permanently widened, chronically infected airways"),
    },
    ("acute_respiratory", "neoplastic"): {
        "Pulmonary neoplasm": _c("Pulmonary neoplasm - lung cancer"),
    },
    ("acute_respiratory", "autoimmune_inflammatory"): {
        "Sarcoidosis": _c("Sarcoidosis"),
    },
    ("acute_respiratory", "degenerative_functional"): {
        "Acute COPD exacerbation / infection": _c("Acute COPD exacerbation"),
        "Bronchospasm / acute asthma exacerbation": _c("Bronchospasm or acute asthma exacerbation"),
        "Larygospasm": _c("Laryngospasm - sudden reflex closure of the vocal cords"),
    },

    # ---- ENT / upper airway ----------------------------------------------
    ("ent_upper_airway", "infective"): {
        "Acute otitis media": _c("Acute otitis media - middle ear infection, ear pain"),
        "Acute rhinosinusitis": _c("Acute rhinosinusitis - facial pain and blocked nose, under 12 weeks"),
        "Chronic rhinosinusitis": _c("Chronic rhinosinusitis - nasal blockage and discharge lasting over 12 weeks"),
        "Viral pharyngitis": _c("Viral pharyngitis - sore throat"),
        "Acute laryngitis": _c("Acute laryngitis - hoarse or lost voice"),
        "Epiglottitis": _c("Epiglottitis - severe sore throat, drooling, muffled voice"),
        "URTI": _c("Upper respiratory tract infection (common cold)"),
        "Croup": _c("Croup - barking cough and stridor in a young child"),
    },
    ("ent_upper_airway", "allergic_hypersensitivity"): {
        "Allergic sinusitis": _c("Allergic sinusitis - sneezing, itch, clear discharge, seasonal or trigger-related"),
    },
    ("ent_upper_airway", "degenerative_functional"): {
        "Chronic rhinosinusitis": _c("Chronic rhinosinusitis - long-standing nasal blockage and discharge"),
        "Larygospasm": _c("Laryngospasm - sudden reflex closure of the vocal cords"),
    },

    # ---- chest pain --------------------------------------------------------
    ("chest_pain", "vascular"): {
        "Possible NSTEMI / STEMI": _c("Heart attack - NSTEMI or STEMI"),
        "Unstable angina": _c("Unstable angina - cardiac chest pain at rest or worsening"),
        "Stable angina": _c("Stable angina - cardiac chest pain predictably on exertion, relieved by rest"),
        "Pulmonary embolism": _c("Pulmonary embolism - clot in the lung arteries"),
    },
    ("chest_pain", "infective"): {
        "Pericarditis": _c("Pericarditis - inflamed heart lining, sharp pain worse lying flat"),
        "Myocarditis": _c("Myocarditis - inflamed heart muscle"),
        "Pneumonia": _c("Pneumonia with pleuritic chest pain"),
    },
    ("chest_pain", "autoimmune_inflammatory"): {
        "Pericarditis": _c("Pericarditis - inflamed heart lining"),
        "Myocarditis": _c("Myocarditis - inflamed heart muscle"),
    },
    ("chest_pain", "structural_surgical"): {
        "Spontaneous pneumothorax": _c("Spontaneous pneumothorax - collapsed lung"),
        "Spontaneous rib fracture": _c("Spontaneous rib fracture - localised chest wall pain and tenderness"),
        "Boerhaave": _c("Boerhaave syndrome - oesophageal rupture after forceful vomiting"),
    },
    ("chest_pain", "degenerative_functional"): {
        "GERD": _c("Gastro-oesophageal reflux - burning retrosternal pain, acid taste, worse lying down"),
    },
    ("chest_pain", "psychological_functional"): {
        "Panic attack": _c("Panic attack - sudden fear, palpitations, tingling, breathlessness"),
    },

    # ---- cardiovascular ----------------------------------------------------
    ("cardiovascular", "arrhythmic_electrical"): {
        "Atrial fibrillation": _c("Atrial fibrillation - irregularly irregular palpitations"),
        "PSVT": _c("Paroxysmal supraventricular tachycardia - sudden fast regular palpitations"),
    },
    # palpitations are frequently described as chest symptoms, and panic and
    # arrhythmia are the classic pair that must be separated
    ("chest_pain", "arrhythmic_electrical"): {
        "Atrial fibrillation": _c("Atrial fibrillation - irregular palpitations with chest discomfort"),
        "PSVT": _c("Paroxysmal supraventricular tachycardia - sudden fast regular palpitations"),
    },
    ("psychiatric_functional", "arrhythmic_electrical"): {
        "PSVT": _c("Paroxysmal supraventricular tachycardia - sudden palpitations mistaken for panic"),
        "Atrial fibrillation": _c("Atrial fibrillation - irregular palpitations mistaken for anxiety"),
    },
    ("acute_respiratory", "arrhythmic_electrical"): {
        "Atrial fibrillation": _c("Atrial fibrillation causing breathlessness"),
        "PSVT": _c("Paroxysmal supraventricular tachycardia causing breathlessness"),
    },
    ("cardiovascular", "vascular"): {
        "Possible NSTEMI / STEMI": _c("Heart attack - NSTEMI or STEMI"),
        "Acute pulmonary edema": _c("Acute pulmonary edema - fluid in the lungs from heart failure"),
        "Pulmonary embolism": _c("Pulmonary embolism - clot in the lung arteries"),
        "Unstable angina": _c("Unstable angina"),
        "Stable angina": _c("Stable angina"),
        "Localized edema": _c("Localised oedema - swelling of a limb or region from venous, lymphatic or allergic cause"),
    },
    ("cardiovascular", "deficiency_nutritional"): {
        "Anemia": _c("Anaemia - low haemoglobin causing palpitations, breathlessness and fatigue"),
    },
    ("cardiovascular", "allergic_hypersensitivity"): {
        "Localized edema": _c("Localised oedema or angioedema"),
        "Anaphylaxis": _c("Anaphylaxis - collapse with swelling after an allergen"),
    },
    ("cardiovascular", "infective"): {
        "Myocarditis": _c("Myocarditis - inflamed heart muscle"),
        "Pericarditis": _c("Pericarditis - inflamed heart lining"),
        "Chagas": _c("Chagas disease - American trypanosomiasis, heart involvement"),
    },

    # ---- abdominal ---------------------------------------------------------
    ("acute_abdominal", "structural_surgical"): {
        "Inguinal hernia": _c("Inguinal hernia - groin lump, worse on straining"),
        "Boerhaave": _c("Boerhaave syndrome - oesophageal rupture after forceful vomiting"),
    },
    ("acute_abdominal", "degenerative_functional"): {
        "GERD": _c("Gastro-oesophageal reflux - heartburn and acid regurgitation"),
    },
    ("acute_abdominal", "neoplastic"): {
        "Pancreatic neoplasm": _c("Pancreatic neoplasm - pancreatic cancer"),
    },

    # ---- neurological ------------------------------------------------------
    ("acute_neurological", "toxic_drug"): {
        "Acute dystonic reactions": _c("Acute dystonic reaction - abnormal sustained muscle spasms after a drug, often antipsychotic or antiemetic"),
    },
    ("acute_neurological", "autoimmune_inflammatory"): {
        "Guillain-Barré syndrome": _c("Guillain-Barre syndrome - ascending weakness after an infection"),
        "Myasthenia gravis": _c("Myasthenia gravis - fatigable weakness, droopy eyelids, double vision"),
    },
    ("acute_neurological", "degenerative_functional"): {
        "Cluster headache": _c("Cluster headache - severe one-sided headache around the eye with tearing and nasal blockage"),
    },

    # ---- haematological ----------------------------------------------------
    ("haematological", "deficiency_nutritional"): {
        "Anemia": _c("Anaemia - low haemoglobin causing pallor, fatigue and breathlessness"),
    },
    ("haematological", "vascular"): {
        "Anemia": _c("Anaemia from blood loss"),
        "Localized edema": _c("Localised oedema from venous or lymphatic obstruction"),
    },
    ("skin_soft_tissue", "degenerative_functional"): {
        "Localized edema": _c("Localised oedema - chronic venous or lymphatic swelling"),
    },
    ("haematological", "neoplastic"): {
        "Anemia": _c("Anaemia secondary to a blood or marrow malignancy"),
        "Pancreatic neoplasm": _c("Pancreatic neoplasm presenting with anaemia and weight loss"),
    },

    # ---- musculoskeletal ---------------------------------------------------
    ("musculoskeletal", "autoimmune_inflammatory"): {
        "SLE": _c("Systemic lupus erythematosus"),
        "Sarcoidosis": _c("Sarcoidosis"),
    },
    ("musculoskeletal", "structural_surgical"): {
        "Spontaneous rib fracture": _c("Spontaneous rib fracture"),
    },

    # ---- skin / soft tissue ------------------------------------------------
    ("skin_soft_tissue", "allergic_hypersensitivity"): {
        "Localized edema": _c("Localised oedema or angioedema - focal swelling"),
        "Anaphylaxis": _c("Anaphylaxis - rapid swelling, rash and collapse after an allergen"),
    },
    ("skin_soft_tissue", "vascular"): {
        "Localized edema": _c("Localised oedema - focal swelling from venous or lymphatic cause"),
    },
    ("skin_soft_tissue", "toxic_drug"): {
        "Scombroid food poisoning": _c("Scombroid food poisoning - flushing, rash and headache shortly after eating spoiled fish"),
    },

    # ---- allergic ----------------------------------------------------------
    ("allergic_reaction", "allergic_hypersensitivity"): {
        "Anaphylaxis": _c("Anaphylaxis - airway swelling, wheeze and collapse after an allergen"),
        "Localized edema": _c("Localised oedema or angioedema without collapse"),
        "Allergic sinusitis": _c("Allergic sinusitis - sneezing, itch, clear nasal discharge"),
    },
    ("allergic_reaction", "toxic_drug"): {
        "Scombroid food poisoning": _c("Scombroid food poisoning - histamine reaction to spoiled fish, mimics allergy"),
    },

    # ---- psychiatric / functional -----------------------------------------
    ("psychiatric_functional", "psychological_functional"): {
        "Panic attack": _c("Panic attack - sudden intense fear with palpitations, tingling and breathlessness"),
    },

    # ---- febrile / systemic infection -------------------------------------
    ("acute_febrile_undifferentiated", "infective"): {
        "Influenza": _c("Influenza", incubation=(1, 4)),
        "HIV (initial infection)": _c("Acute HIV seroconversion illness", incubation=(14, 28)),
        "Ebola": _c("Ebola virus disease", incubation=(2, 21)),
        "Chagas": _c("Chagas disease - American trypanosomiasis"),
        "Tuberculosis": _c("Tuberculosis", incubation=(30, 3650)),
        "Pneumonia": _c("Pneumonia"),
        "URTI": _c("Upper respiratory tract infection"),
    },
    ("acute_febrile_undifferentiated", "autoimmune_inflammatory"): {
        "SLE": _c("Systemic lupus erythematosus"),
        "Sarcoidosis": _c("Sarcoidosis"),
        "Myocarditis": _c("Myocarditis"),
        "Pericarditis": _c("Pericarditis"),
    },

    # ---- constitutional / chronic -----------------------------------------
    ("constitutional_chronic", "neoplastic"): {
        "Pancreatic neoplasm": _c("Pancreatic neoplasm - pancreatic cancer"),
        "Pulmonary neoplasm": _c("Pulmonary neoplasm - lung cancer"),
    },
    ("constitutional_chronic", "infective"): {
        "Tuberculosis": _c("Tuberculosis", incubation=(30, 3650)),
        "HIV (initial infection)": _c("HIV infection"),
        "Chagas": _c("Chagas disease"),
    },
    ("constitutional_chronic", "autoimmune_inflammatory"): {
        "SLE": _c("Systemic lupus erythematosus"),
        "Sarcoidosis": _c("Sarcoidosis"),
    },
    ("constitutional_chronic", "deficiency_nutritional"): {
        "Anemia": _c("Anaemia - low haemoglobin"),
    },
}


GRIDS = {"tropical": TROPICAL, "ddxplus": DDXPLUS}
