# -*- coding: utf-8 -*-
"""Public training data: downloads the TRAIN splits of four open PII datasets and converts them to the
format and the label set of this project (data/external/<name>.jsonl, same shape as data/train.jsonl).

  python external_data.py download      fetch the raw files into data/external/raw (about 900 MB)
  python external_data.py convert       write data/external/<name>.jsonl and print what was mapped

Sources (all synthetic, no real personal data; test splits are never touched, they are what
benchmark.py measures on):

  ai4privacy   ai4privacy/pii-masking-openpii-1m       CC BY 4.0     23 languages, 19 labels
  nemotron     nvidia/Nemotron-PII                     CC BY 4.0     English, 55 labels
  gretel       gretelai/gretel-pii-masking-en-v1       Apache 2.0    English, domain documents
  privy        piimb/privy (from beki/privy)           MIT           English, JSON / SQL / protocol traces
  mapa         dglover1/mapa-eur-lex (MAPA project)    CC BY 4.0     EUR-Lex court documents in 21 languages, annotated by hand

The documents of mapa that the benchmark is built on (its test split) are never used: only the train and validation
splits, which are different court cases, and without any sentence that also occurs word for word in the test split.

A label of a source that has no counterpart here is dropped (the text stays, unlabelled). Adjacent
pieces of the same thing are joined ("John" + "Smith" -> one PERSONA, "42" + "Rue de Rivoli" -> one
INDIRIZZO), so placeholders come out one per person and one per address.
"""
import collections
import json
import random
import re
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "data" / "external"
RAW = OUT / "raw"
HUB = "https://huggingface.co/datasets/"
PARQUET = {
    "nemotron": HUB + "nvidia/Nemotron-PII/resolve/refs%2Fconvert%2Fparquet/default/train/0000.parquet",
    "gretel": HUB + "gretelai/gretel-pii-masking-en-v1/resolve/refs%2Fconvert%2Fparquet/default/train/0000.parquet",
    "privy": HUB + "piimb/privy/resolve/refs%2Fconvert%2Fparquet/privy-small/train/0000.parquet",
}
MORE = {     # added with the second round of sources: (file name in data/external/raw, address)
    "finance": ("finance.parquet", HUB + "gretelai/synthetic_pii_finance_multilingual/resolve/main/data/train-00000-of-00001.parquet"),
    "nym": ("nym.jsonl", HUB + "Wismut/nym-pii-multilingual-data/resolve/main/train.jsonl"),
    "tab": ("tab.parquet", HUB + "mattmdjaga/text-anonymization-benchmark-train/resolve/main/data/train-00000-of-00001.parquet"),
    "urchade": ("urchade.json", HUB + "urchade/synthetic-pii-ner-mistral-v1/resolve/main/data.json"),
}
MAPA = HUB + "dglover1/mapa-eur-lex/resolve/refs%2Fconvert%2Fparquet/default/{part}/0000.parquet"
AI4PRIVACY = HUB + "ai4privacy/pii-masking-openpii-1m/resolve/main/data/train.jsonl"
AI4PRIVACY_SLICES, SLICE_BYTES = 14, 45_000_000     # evenly spaced pieces of the 3.7 GB file: every language, a sixth of the size

LABELS = {
    "ai4privacy": {
        "GIVENNAME": "PERSONA", "SURNAME": "PERSONA", "TITLE": "TITOLO", "EMAIL": "EMAIL", "TELEPHONENUM": "TELEFONO",
        "STREET": "INDIRIZZO", "BUILDINGNUM": "INDIRIZZO", "CITY": "CITTA", "ZIPCODE": "CAP", "DATE": "DATA", "AGE": "ETA",
        "GENDER": "GENERE", "SEX": "GENERE", "CREDITCARDNUMBER": "CARTA", "IDCARDNUM": "DOC_ID", "PASSPORTNUM": "DOC_ID",
        "DRIVERLICENSENUM": "DOC_ID", "TAXNUM": "CF", "SOCIALNUM": "CF",
    },
    "nemotron": {
        "first_name": "PERSONA", "last_name": "PERSONA", "name": "PERSONA", "company_name": "ORG", "email": "EMAIL",
        "phone_number": "TELEFONO", "fax_number": "TELEFONO", "street_address": "INDIRIZZO", "address": "INDIRIZZO", "city": "CITTA",
        "state": "LUOGO", "county": "LUOGO", "country": "LUOGO", "coordinate": "LUOGO", "postcode": "CAP",
        "date_of_birth": "DATA_NASCITA", "date": "DATA", "date_time": "DATA", "time": "ORA", "age": "ETA", "gender": "GENERE",
        "occupation": "PROFESSIONE", "employment_status": "PROFESSIONE", "education_level": "ISTRUZIONE",
        "race_ethnicity": "ORIGINE", "nationality": "ORIGINE", "language": "ORIGINE", "religious_belief": "RELIGIONE",
        "political_view": "POLITICA", "sexuality": "ORIENTAMENTO", "blood_type": "SALUTE", "url": "URL", "ipv4": "IP", "ipv6": "IP",
        "mac_address": "MAC", "user_name": "ACCOUNT", "password": "SEGRETO", "api_key": "SEGRETO", "pin": "SEGRETO",
        "http_cookie": "SEGRETO", "account_number": "IBAN", "bank_routing_number": "IBAN", "swift_bic": "IBAN",
        "credit_debit_card": "CARTA", "credit_card_number": "CARTA", "cvv": "CARTA_SEC", "ssn": "CF", "national_id": "CF",
        "tax_id": "CF", "certificate_license_number": "DOC_ID", "biometric_identifier": "DOC_ID", "license_plate": "TARGA",
        "vehicle_identifier": "ID_VEICOLO", "customer_id": "ID_PRATICA", "employee_id": "ID_PRATICA", "unique_id": "ID_PRATICA",
        "unique_identifier": "ID_PRATICA", "medical_record_number": "ID_PRATICA", "health_plan_beneficiary_number": "ID_PRATICA",
        "device_identifier": "ID_DISPOSITIVO",
    },
    "privy": {
        "PERSON": "PERSONA", "PER": "PERSONA", "EMAIL_ADDRESS": "EMAIL", "PHONE_NUMBER": "TELEFONO", "STREET_ADDRESS": "INDIRIZZO",
        "LOCATION": "LUOGO", "LOC": "LUOGO", "GPE": "LUOGO", "COORDINATE": "LUOGO", "ZIP_CODE": "CAP", "DATE_TIME": "DATA",
        "AGE": "ETA", "TITLE": "TITOLO", "NRP": "ORIGINE", "ORGANIZATION": "ORG", "ORG": "ORG", "URL": "URL", "DOMAIN_NAME": "DOMINIO",
        "IP_ADDRESS": "IP", "MAC_ADDRESS": "MAC", "PASSWORD": "SEGRETO", "IBAN_CODE": "IBAN", "US_BANK_NUMBER": "IBAN",
        "ROUTING_NUMBER": "IBAN", "SWIFT_CODE": "IBAN", "CREDIT_CARD": "CARTA", "US_SSN": "CF", "US_ITIN": "CF",
        "US_PASSPORT": "DOC_ID", "US_DRIVER_LICENSE": "DOC_ID", "LICENSE_PLATE": "TARGA", "IMEI": "ID_DISPOSITIVO",
    },
}
LABELS["gretel"] = LABELS["nemotron"]
# mapa: dates come as one span (coarse label), the rest by fine label. Courts and institutions (ORGANISATION) and sums
# of money are not personal data here; marital status has no counterpart.
LABELS["mapa"] = {"DATE": "DATA", "TIME": "ORA", "FAMILY NAME": "PERSONA", "INITIAL NAME": "PERSONA", "GIVEN NAME": "PERSONA",
                  "GIVEN NAME - MALE": "PERSONA", "GIVEN NAME - FEMALE": "PERSONA", "ROLE": "PROFESSIONE", "PROFESSION": "PROFESSIONE",
                  "TITLE": "TITOLO", "AGE": "ETA", "NATIONALITY": "ORIGINE", "ETHNIC CATEGORY": "ORIGINE", "CITY": "CITTA",
                  "COUNTRY": "LUOGO", "TERRITORY": "LUOGO", "PLACE": "LUOGO", "BUILDING": "INDIRIZZO", "STREET": "INDIRIZZO",
                  "POSTCODE": "CAP", "URL": "URL", "EMAIL": "EMAIL", "TELEPHONE NUMBER": "TELEFONO"}
LABELS["finance"] = {
    "name": "PERSONA", "first_name": "PERSONA", "last_name": "PERSONA", "company": "ORG", "date": "DATA", "date_time": "DATA",
    "time": "ORA", "date_of_birth": "DATA_NASCITA", "street_address": "INDIRIZZO", "email": "EMAIL", "phone_number": "TELEFONO",
    "iban": "IBAN", "bban": "IBAN", "swift_bic_code": "IBAN", "bank_routing_number": "IBAN", "customer_id": "ID_PRATICA",
    "employee_id": "ID_PRATICA", "ipv4": "IP", "ipv6": "IP", "passport_number": "DOC_ID", "driver_license_number": "DOC_ID",
    "ssn": "CF", "credit_card_number": "CARTA", "credit_card_security_code": "CARTA_SEC", "account_pin": "SEGRETO",
    "api_key": "SEGRETO", "password": "SEGRETO", "user_name": "ACCOUNT", "local_latlng": "LUOGO",
}
LABELS["nym"] = {
    "GIVEN_NAME": "PERSONA", "SURNAME": "PERSONA", "DATE": "DATA", "DATE_OF_BIRTH": "DATA_NASCITA", "TIME": "ORA", "AGE": "ETA",
    "GENDER": "GENERE", "PHONE": "TELEFONO", "FAX_NUMBER": "TELEFONO", "EMAIL": "EMAIL", "STREET_ADDRESS": "INDIRIZZO",
    "BUILDING_NUMBER": "INDIRIZZO", "STREET_NAME": "INDIRIZZO", "SECONDARY_ADDRESS": "INDIRIZZO", "CITY": "CITTA", "ZIP_CODE": "CAP",
    "COUNTRY": "LUOGO", "STATE": "LUOGO", "COMPANY_NAME": "ORG", "CUSTOMER_ID": "ID_PRATICA", "EMPLOYEE_ID": "ID_PRATICA",
    "MEDICAL_RECORD_NUMBER": "ID_PRATICA", "GOVERNMENT_ID": "CF", "TAX_ID": "CF", "SSN": "CF", "PASSPORT": "DOC_ID",
    "DRIVERS_LICENSE": "DOC_ID", "ACCOUNT_NUMBER": "IBAN", "IBAN": "IBAN", "SWIFT_BIC": "IBAN", "ROUTING_NUMBER": "IBAN",
    "CREDIT_DEBIT_CARD": "CARTA", "CVV": "CARTA_SEC", "LICENSE_PLATE": "TARGA", "PASSWORD": "SEGRETO", "API_KEY": "SEGRETO",
    "PIN": "SEGRETO", "USERNAME": "ACCOUNT", "MAC_ADDRESS": "MAC", "URL": "URL",
}
# tab (court cases annotated by hand): every mention has a type and a verdict of the annotator, "has to be masked to
# protect the applicant" (DIRECT, QUASI) or not (NO_MASK). What had to be masked takes our label; what did not is left
# open for people, places and dates (a name is a name here, whoever it belongs to) and is a certain "nothing" for
# organisations (the Court, a ministry, a state: exactly the public bodies this project does not mask). An organisation
# that had to be masked is left open too: it is as often a local court as a company. Demographic traits, sums and the
# rest have no single counterpart and are dropped.
LABELS["tab"] = {"PERSON": "PERSONA", "TITLE": "TITOLO", "DATETIME": "DATA", "LOC": "LUOGO", "CODE": "ID_PRATICA"}
TAB_OPEN = {"PERSON": "PERSONA", "DATETIME": "DATA", "LOC": "CITTA"}
TAB_TITLE = re.compile(r"(Mr|Mrs|Ms|Miss|Dr|Prof|Professor|Sir|Lord|Lady|Dame|Baroness)\.?\s+(?=\S)")
TAB_ROLE = re.compile(r"(Judge|Justice|President|Vice-President|Registrar|Section Registrar|Deputy Registrar)\s+(?=[A-Z])")
# urchade: thousands of free-form types ("health insurance id number", "CPF"...), told apart by keyword, first match wins.
# Only examples of what something is: nothing is said about the rest of the text (build_train.py leaves it all open).
URCHADE = [(re.compile(p), label) for p, label in (
    (r"birth|\bdob\b", "DATA_NASCITA"), (r"e-?mail", "EMAIL"), (r"\bip\b|ipv[46]", "IP"), (r"\bmac address", "MAC"),
    (r"expir", "-"), (r"licen[cs]e plate|number plate|vehicle registration", "TARGA"),
    (r"company registration|business registration|\bvat\b|\bcnpj\b", "PIVA"),
    (r"social security|\bssn\b|\btax\b|\bcpf\b|national id|national insurance|personal identification number|fiscal|\bnif\b|"
     r"\bdni\b|\bcurp\b|\bnie\b", "CF"),
    (r"passport|driver|identity card|\bid card\b|identity document|identification card|^rg$", "DOC_ID"),
    (r"security code|\bcvv\b|\bcvc\b", "CARTA_SEC"), (r"credit card|debit card|bank card|payment card|^card number$", "CARTA"),
    (r"insurance|medical record|patient id|policy number|student id|employee id|customer id|membership|registration number",
     "ID_PRATICA"),
    (r"\biban\b|bank account|account number|\bswift\b|\bbic\b|routing", "IBAN"),
    (r"phone|mobile|\bfax\b|\bcell\b", "TELEFONO"), (r"password|api key|\btoken\b|^pin$|\bsecret\b", "SEGRETO"),
    (r"user ?name|\blogin\b|social media handle", "ACCOUNT"), (r"^(url|website|web address)$", "URL"),
    (r"^(person|name|full name|first name|last name|surname|given name|person name|individual)$", "PERSONA"),
    (r"^(organization|organisation|company|company name)$", "?ORG"),
    (r"address|^street", "INDIRIZZO"), (r"^(city|town)$", "CITTA"), (r"^(country|state|region|province|location|place)$", "LUOGO"),
    (r"^(date|date time|datetime)$", "DATA"), (r"^time$", "ORA"), (r"^age$", "ETA"), (r"nationality|ethnicity", "ORIGINE"),
    (r"^(occupation|profession|job title|job)$", "PROFESSIONE"), (r"^(gender|sex)$", "GENERE"), (r"religio", "RELIGIONE"),
    (r"political", "POLITICA"), (r"sexual orientation", "ORIENTAMENTO"),
    (r"medication|medical condition|^condition$|disease|diagnosis|allerg|illness|symptom|blood type|^drug$|disorder", "SALUTE"),
)]
JOIN = {"PERSONA", "INDIRIZZO"}
# a date that the text itself presents as a birth date keeps the more specific label
BIRTH = re.compile(r"(?<!\w)(?:born|birth\w*|d\.?o\.?b\.?|nat[oa]|nascita|née?|naissance|geboren|geb\.|geburt\w*|nacid[oa]|nacimiento|"
                   r"nascid[oa]|nascimento|geboorte\w*|urodz\w*|narozen\w*|narod\w*|født|fødsel\w*|född|födelse\w*|syntynyt|syntymä\w*|"
                   r"sündinud|sünni\w*|gimęs|gimim\w*|dzim\w*|rođen\w*|rojen\w*|rojstv\w*|născut\w*|na[sș]ter\w*|született|születés\w*|"
                   r"γεννη\w*|γέννησ\w*|ражда\w*|роден\w*|рођен\w*)(?!\w)", re.I)
# a label of a source that covers two of ours: the first is taken, the second stays allowed (train.py does not punish it)
ALSO = {("privy", "LOCATION"): "CITTA", ("privy", "LOC"): "CITTA", ("privy", "GPE"): "CITTA", ("nemotron", "address"): "CITTA",
        ("finance", "street_address"): "CITTA", ("tab", "LOC"): "CITTA"}
# privy calls TITLE both "Mr." and "female", and NRP both a nationality and a religion: told apart by the value
GENDERS = {"male", "female", "m", "f", "man", "woman", "non-binary", "nonbinary", "other", "masculine", "feminine"}
FAITHS = re.compile(r"(christian|catholic|protestant|buddhis|hindu|muslim|islam|jewish|judaism|sikh|atheis|agnostic|orthodox|lutheran|"
                    r"baptist|methodist|mormon|taois|shinto|jain|evangelical|anglican|presbyterian)", re.I)


HONORIFICS = re.compile(r"^(mr|mrs|ms|miss|mx|dr|prof|sir|madam|mme|mlle|m|herr|frau|sig|sig\.ra|dott|dott\.ssa|sr|sra|srta)\.?$", re.I)
NOT_A_JOB = re.compile(r"\b(department|office|division|team|unit|services|committee|board|bureau|agency|group)\b", re.I)


def refine(name, label, value):
    if name == "privy" and label == "TITLE" and value.strip().lower() in GENDERS:
        return "GENERE"
    if name == "privy" and label == "TITLE" and not HONORIFICS.match(value.strip()):
        return "-"           # privy puts under TITLE whatever a "title" field holds: only real honorifics are kept
    if label == "occupation" and NOT_A_JOB.search(value):
        return "-"           # "Identity Verification Department" is where someone works, not what they do
    if name == "privy" and label == "NRP" and FAITHS.search(value):
        return "RELIGIONE"
    return None


def fetch(url, target, first=None, last=None):
    request = urllib.request.Request(url, headers={"User-Agent": "omissis-training", **({"Range": f"bytes={first}-{last}"} if first is not None else {})})
    with urllib.request.urlopen(request, timeout=180) as answer, open(target.with_suffix(".part"), "wb") as out:
        while chunk := answer.read(1 << 20):
            out.write(chunk)
    target.with_suffix(".part").replace(target)


def download():
    RAW.mkdir(parents=True, exist_ok=True)
    for name, url in PARQUET.items():
        target = RAW / f"{name}.parquet"
        if not target.exists():
            print(f"downloading {name} …", flush=True)
            fetch(url, target)
    for part in ("train", "validation", "test"):     # test: only to leave out of the training set what also occurs there
        target = RAW / f"mapa_{part}.parquet"
        if not target.exists():
            print(f"downloading mapa {part} …", flush=True)
            fetch(MAPA.format(part=part), target)
    for name, (file, url) in MORE.items():
        if not (RAW / file).exists():
            print(f"downloading {name} …", flush=True)
            fetch(url, RAW / file)
    with urllib.request.urlopen(urllib.request.Request(AI4PRIVACY, method="HEAD", headers={"User-Agent": "omissis-training"}), timeout=60) as answer:
        size = int(answer.headers["Content-Length"])
    for i in range(AI4PRIVACY_SLICES):
        target = RAW / f"ai4privacy_{i:02}.jsonl"
        if not target.exists():
            start = i * (size // AI4PRIVACY_SLICES)
            print(f"downloading ai4privacy, piece {i + 1} of {AI4PRIVACY_SLICES} …", flush=True)
            fetch(AI4PRIVACY, target, start, min(size - 1, start + SLICE_BYTES - 1))
    print("raw files:", ", ".join(f"{f.name} {f.stat().st_size / 1e6:.0f} MB" for f in sorted(RAW.iterdir())))


def spans_from(name, text, entities, mapping, dropped, also):
    """[(start, end, source label)] -> sorted, non-overlapping [[start, end, our label]], with adjacent pieces joined."""
    out = []
    for start, end, label in sorted(entities):
        ours = refine(name, label, text[max(0, start):end]) or mapping.get(label)
        if ours is None or ours == "-":
            dropped[label] += 1
            continue
        start, end = max(0, start), min(len(text), end)
        while start < end and text[start].isspace():
            start += 1
        while end > start and text[end - 1].isspace():
            end -= 1
        if start >= end or (out and start < out[-1][1]):
            continue
        if ours == "DATA" and (BIRTH.search(text[max(0, start - 60):start]) or BIRTH.match(text[end:end + 20].lstrip(" ,;:(-–"))):
            ours = "DATA_NASCITA"
        if out and out[-1][2] == ours and ours in JOIN and text[out[-1][1]:start] in (" ", ", ", "  "):
            out[-1][1] = end
        else:
            out.append([start, end, ours])
            if (name, label) in ALSO and refine(name, label, text[start:end]) is None:
                also.append([start, end, ALSO[(name, label)]])
    return out


def located(text, pairs):
    """Sources that give only (value, label): every occurrence of the value becomes an entity."""
    found = []
    for value, label in pairs:
        value = str(value)
        if len(value.strip()) < 2:
            continue
        position = text.find(value)
        while position != -1:
            found.append((position, position + len(value), label))
            position = text.find(value, position + len(value))
    return found


def read_ai4privacy():
    for piece in sorted(RAW.glob("ai4privacy_*.jsonl")):
        lines = piece.read_bytes().split(b"\n")[1:-1]     # the first and the last line of a slice are cut in half
        for line in lines:
            try:
                r = json.loads(line)
            except ValueError:
                continue
            yield r["source_text"], [(m["start"], m["end"], m["label"]) for m in r["privacy_mask"]], r.get("language", "")


def read_parquet(name):
    import pyarrow.parquet as pq
    table = pq.read_table(RAW / f"{name}.parquet")
    for r in table.to_pylist():
        if name == "privy":
            yield r["full_text"], [(s["start_position"], s["end_position"], s["entity_type"]) for s in r["spans"]], "en"
            continue
        text = r["text"]
        raw = r.get("spans") or r.get("entities") or "[]"
        try:
            items = json.loads(raw) if isinstance(raw, str) else raw
        except ValueError:
            import ast
            items = ast.literal_eval(raw)
        entities = []
        for e in items:
            if "start" in e and "end" in e:
                entities.append((e["start"], e["end"], e.get("label") or (e.get("types") or [""])[0]))
            else:   # gretel: {"entity": value, "types": [label, ...]}
                entities += located(text, [(e.get("entity") or e.get("text") or "", (e.get("types") or [e.get("label", "")])[0])])
        yield text, entities, "en"


def read_mapa():
    """Sentences of the train and validation splits, with character spans rebuilt from the tokens."""
    import pyarrow.parquet as pq
    flat = lambda s: re.sub(r"\W+", " ", s).strip().lower()   # noqa: E731
    in_test = {flat(r["sentence"]) for r in pq.read_table(RAW / "mapa_test.parquet").to_pylist()}
    skipped = 0
    for part in ("train", "validation"):
        for r in pq.read_table(RAW / f"mapa_{part}.parquet").to_pylist():
            text = r["sentence"]
            if flat(text) in in_test:
                skipped += 1
                continue
            entities, position, current = [], 0, None
            for token, coarse, end in zip(r["tokens"], r["coarse_grained"], r["fine_grained"]):
                at = text.find(token, position)
                if at < 0:
                    current = None
                    continue
                position = at + len(token)
                tag = coarse if coarse[2:] in ("DATE", "TIME") else end
                if tag == "O":
                    current = None
                elif tag.startswith("I-") and current and current[2] == tag[2:]:
                    current[1] = position
                else:
                    current = [at, position, tag[2:]]
                    entities.append(current)
            yield text, [tuple(e) for e in entities], r["language"]
    print(f"  mapa: {skipped:,} sentences left out because they also occur in the test split")


FLAT = lambda s: re.sub(r"\W+", " ", s).strip().lower()   # noqa: E731
SENTENCE = re.compile(r"\n+|(?<=[.!?;])\s+")


def in_benchmark():
    """The sentences of the public benchmark, flattened: a document that contains one of them is left out."""
    file = HERE / "data" / "benchmarks" / "piimb_sentences.jsonl"
    if not file.exists():
        print("  data/benchmarks/piimb_sentences.jsonl is not there: run benchmark.py first, so that what also occurs in the benchmark is left out")
        return set()
    with file.open(encoding="utf-8") as f:
        return {FLAT(t) for t in (json.loads(line)["text"] for line in f if line.strip()) if len(t) > 60}


FIN_DATE = re.compile(r"\d{4}|\d{1,2}[./-]\d{1,2}|(?=.*\d)(?=.*\b(?:jan|feb|f[ée]v|mar|mär|maart|mrt|apr|abr|avr|ma[iyj]|mei|mag|jun|juin|"
                      r"giu|jul|juil|lug|aug|ago|août|sep|set|o[ck]t|ott|nov|de[czs]|dic|gen|ene)\w*)", re.I | re.S)
FIN_TIME = re.compile(r"\d{1,2}[:.h]\d{2}")


def read_finance():
    """Full financial documents in seven languages. The generator sometimes left a field as a placeholder and labelled
    it all the same, and sometimes labelled a value only the first time it occurs: both are put right here."""
    import pyarrow.parquet as pq
    tested = in_benchmark()
    codes = {"English": "en", "Spanish": "es", "Swedish": "sv", "German": "de", "Italian": "it", "France": "fr", "Dutch": "nl"}
    left_out = broken = again = 0
    for r in pq.read_table(RAW / "finance.parquet", columns=["generated_text", "pii_spans", "language"]).to_pylist():
        text = r["generated_text"] or ""
        try:
            entities = [(e["start"], e["end"], e["label"]) for e in json.loads(r["pii_spans"] or "[]")]
        except (ValueError, KeyError, TypeError):
            broken += 1
            continue
        if any(not 0 <= s < e <= len(text) for s, e, _ in entities):
            broken += 1
            continue
        if tested and any(FLAT(p) in tested for p in SENTENCE.split(text) if len(p) > 60):
            left_out += 1
            continue
        entities = [(s, e, l) for s, e, l in entities
                    if l in ("password", "api_key") or not re.search(r"[\[\]<>{}]|_{3,}|\bX{4,}", text[s:e])]
        # the labels were given by a language model, and some are plainly wrong: "fifth year" and "Article 4" as dates,
        # "15 minutes" as a time, the middle of a web address as a company
        entities = [(s, e, l) for s, e, l in entities if not (
            (l in ("date", "date_time") and not FIN_DATE.search(text[s:e])) or (l == "time" and not FIN_TIME.search(text[s:e]))
            or (l in ("company", "name") and (text[max(0, s - 1):s] in (".", "@", "/") or re.match(r"@|\.[a-z]{2,4}\b", text[e:e + 5]))))]
        covered = bytearray(len(text))
        for s, e, _ in entities:
            covered[s:e] = b"\x01" * (e - s)
        for value, label in sorted({(text[s:e], l) for s, e, l in entities if e - s >= 6}):
            for m in re.finditer(r"(?<!\w)" + re.escape(value) + r"(?!\w)", text):
                if not any(covered[m.start():m.end()]):
                    entities.append((m.start(), m.end(), label))
                    covered[m.start():m.end()] = b"\x01" * (m.end() - m.start())
                    again += 1
        yield text, entities, codes.get(r["language"], ""), {}
    print(f"  finance: {left_out:,} documents left out because a sentence of theirs also occurs in the benchmark, {broken:,} with "
          f"spans outside the text; {again:,} repeated values labelled")


# words that tell Italian from the languages closest to it (nym does not say the language of a text)
COMMON = {
    "it": "il di che per con del della dei delle gli nel nella alle sono è nato nata codice numero indirizzo signor signora presso "
          "anche questo nome cognome telefono via e in un una al dal",
    "es": "el los las de que para con del número nombre dirección es fecha y en por una código señor señora teléfono calle un al su",
    "pt": "o os as de que para com do da dos das número nome endereço é em uma não código telefone rua e um ao seu sua",
    "fr": "le les de que pour avec du des numéro nom adresse est et en une né née téléphone rue dans un au sur",
    "ro": "și de la cu pentru este numărul nume adresa din un o în care pe nr",
}
COMMON = {language: set(words.split()) for language, words in COMMON.items()}


def read_nym(share=.14):
    """Templates filled with made-up values, exact by construction, 23 languages. All the Italian texts and one in seven of
    the others: the whole set would be as large as everything else together."""
    r = random.Random(7)
    with open(RAW / "nym.jsonl", encoding="utf-8") as f:
        for line in f:
            d = json.loads(line)
            words = collections.Counter(re.findall(r"[^\W\d_]+", d["text"].lower()))
            score = {language: sum(words[w] for w in common) for language, common in COMMON.items()}
            italian = score["it"] >= 2 and score["it"] > max(v for k, v in score.items() if k != "it")
            if italian or r.random() < share:
                yield d["text"], [(e["start"], e["end"], e["label"]) for e in d["entities"]], "it" if italian else "", {}


A_DATE = re.compile(r"\d{4}|\d{1,2}[./-]\d{1,2}|january|february|march|april|may|june|july|august|september|october|november|december", re.I)


def read_tab():
    """Court cases annotated by hand (see LABELS["tab"]). The first annotator of each document."""
    import pyarrow.parquet as pq
    for r in pq.read_table(RAW / "tab.parquet", columns=["text", "annotations"]).to_pylist():
        text = r["text"]
        mentions = next((v["entity_mentions"] for v in r["annotations"].values() if v and v.get("entity_mentions")), [])
        entities, opened, nothing = [], [], []
        for m in sorted(mentions, key=lambda m: (m["start_offset"], -m["end_offset"])):
            s, e, kind, masked = m["start_offset"], m["end_offset"], m["entity_type"], m["identifier_type"] != "NO_MASK"
            if kind == "ORG":
                opened.append([s, e, "ORG"]) if masked else nothing.append([s, e])
            elif kind == "PERSON":
                title = TAB_TITLE.match(text, s, e)
                role = None if title else TAB_ROLE.match(text, s, e)
                if title:
                    entities.append((s, title.end(), "TITLE"))
                s = title.end() if title else role.end() if role else s
                entities.append((s, e, "PERSON")) if masked else opened.append([s, e, "PERSONA"])
            elif kind in LABELS["tab"]:
                if masked and (kind != "DATETIME" or A_DATE.search(text[s:e])):     # "three years" is not a date
                    entities.append((s, e, kind))
                elif kind in TAB_OPEN:
                    opened.append([s, e, TAB_OPEN[kind]])
        yield text, entities, "en", {"aperti": opened, "nulla": nothing}


GLUED = {"@", "/", "\\", "_", "="}
NO_SPACE_BEFORE = set(",.;:!?)]}%…»”") | {"'s", "’s", "n't"}
NO_SPACE_AFTER = set("([{#$€£«“")
ELIDED = {"s", "t", "ll", "re", "ve", "d", "m"}


def detokenize(tokens):
    """urchade gives the words one by one: the text is put back together the way it is normally written, as far as it can
    be told (no space before a comma, "example . com" -> "example.com", "l ' homme" -> "l'homme").
    Returns the text and where each word starts and ends in it."""
    parts, starts, ends, position, quote_open = [], [], [], 0, {}
    glue_next = False
    for i, token in enumerate(tokens):
        before = tokens[i - 1] if i else ""
        after = tokens[i + 1] if i + 1 < len(tokens) else ""
        space, glue_after = i > 0 and not glue_next, False
        if token in GLUED:
            space, glue_after = False, True
        elif token == ".":
            space = False
            glue_after = bool(after) and (after[0].islower() or after[0].isdigit()) and before[-1:].isalnum()
        elif token == ":":
            space = False
            glue_after = (before.isdigit() and after.isdigit()) or after == "/"
        elif token == "+" and after[:1].isdigit():
            glue_after = True
        elif token in ("'", "’"):
            if after.lower() in ELIDED or (before.isalpha() and len(before) <= 2) or before.lower().endswith(("ll", "qu", "un")):
                space, glue_after = False, True
            else:      # a quotation mark: opens before a word, closes after it
                quote_open[token] = not quote_open.get(token, False)
                space, glue_after = (space, True) if quote_open[token] else (False, False)
        elif token == '"':
            quote_open[token] = not quote_open.get(token, False)
            space, glue_after = (space, True) if quote_open[token] else (False, False)
        elif token in NO_SPACE_BEFORE:
            space = False
        elif token in NO_SPACE_AFTER:
            glue_after = True
        if space:
            parts.append(" ")
            position += 1
        starts.append(position)
        parts.append(token)
        position += len(token)
        ends.append(position)
        glue_next = glue_after
    return "".join(parts), starts, ends


def read_urchade():
    """Short texts in several languages with free-form types (see URCHADE)."""
    for d in json.loads((RAW / "urchade.json").read_text(encoding="utf-8")):
        text, starts, ends = detokenize(d["tokenized_text"])
        entities, opened = [], []
        for first, last, kind in d["ner"]:
            kind = kind.lower().replace("_", " ").strip()
            ours = next((label for pattern, label in URCHADE if pattern.search(kind)), "-")
            if ours == "-" or not 0 <= first <= last < len(starts):
                continue
            if ours[0] == "?":
                opened.append([starts[first], ends[last], ours[1:]])
            else:
                entities.append((starts[first], ends[last], ours))
        if entities:
            yield text, entities, "", {"aperti": opened}


LABELS["urchade"] = {label: label for _, label in URCHADE if label[0] not in "?-"}
READERS = {"ai4privacy": read_ai4privacy, "mapa": read_mapa, "finance": read_finance, "nym": read_nym, "tab": read_tab,
           "urchade": read_urchade}
SOURCES = ("ai4privacy", "nemotron", "gretel", "privy", "mapa", "finance", "nym", "tab", "urchade")


def convert(only=()):
    OUT.mkdir(parents=True, exist_ok=True)
    r = random.Random(41)
    for name in only or SOURCES:
        rows = READERS[name]() if name in READERS else read_parquet(name)
        dropped, kept, languages, n, characters = collections.Counter(), collections.Counter(), collections.Counter(), 0, 0
        seen = set()
        with (OUT / f"{name}.jsonl").open("w", encoding="utf-8") as out:
            for text, entities, language, *more in rows:
                if not text or not text.strip() or hash(text) in seen:
                    continue
                seen.add(hash(text))
                also = []
                spans = spans_from(name, text, entities, LABELS[name], dropped, also)
                kept.update(label for _, _, label in spans)
                languages[language] += 1
                n += 1
                characters += len(text)
                # "aperti": places where a label may be but is not given (no penalty either way); "nulla": places where
                # the source says that there is nothing to mask
                extra = {}
                for key, places in (more[0] if more else {}).items():
                    places = [p for p in places if 0 <= p[0] < p[1] <= len(text) and not any(p[0] < e and s < p[1] for s, e, _ in spans)]
                    if places:
                        extra[key] = places
                        kept.update(f"({key})" for _ in places)
                out.write(json.dumps({"testo": text, "spans": spans, "forma": name, "lingua": language, **({"anche": also} if also else {}),
                                      **extra}, ensure_ascii=False) + "\n")
        print(f"\n{name}: {n:,} texts, {characters / max(1, n):.0f} characters on average, {sum(kept.values()):,} entities")
        print("  labels:", dict(kept.most_common()))
        if dropped:
            print("  dropped (no counterpart):", dict(dropped.most_common()))
        if len(languages) > 1:
            print("  languages:", dict(languages.most_common()))
    r.random()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:2] == ["convert"]:
        convert(sys.argv[2:])        # with names after it, only those sources
    else:
        download()
