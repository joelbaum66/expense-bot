import base64
import json
import re

import anthropic

client = anthropic.Anthropic()

SYSTEM_PROMPT = """Tu es un expert-comptable français. Tu analyses des reçus et messages de dépenses professionnelles.
Tu extrais les informations et les retournes en JSON strict, sans aucun texte supplémentaire.

Règles de catégorisation :
- restaurant, repas, déjeuner, dîner, café, brasserie, pizzeria, sushi → "Repas"
- station, essence, carburant, fuel, péage → "Transport"
- taxi, uber, bolt, train, sncf, avion, air france, ratp, metro, bus → "Transport"
- hôtel, airbnb, booking, hébergement → "Hébergement"
- fournitures, matériel, bureau, imprimante, papier, stylo → "Fournitures"
- tout autre mot → "Autre"

Taux de TVA français : 20% (standard), 10% (restauration, transport), 5.5% (alimentation), 2.1% (presse médicaments).

Retourne UNIQUEMENT ce JSON (pas de markdown, pas d'explication) :
{
  "date": "JJ/MM/AAAA",
  "marchand": "Nom du marchand",
  "categorie": "Repas|Transport|Hébergement|Fournitures|Autre",
  "ht": 0.00,
  "tva_pct": 20.0,
  "tva_eur": 0.00,
  "ttc": 0.00,
  "devise": "EUR"
}

Calculs :
- Si TTC et TVA% connus : HT = TTC / (1 + TVA%/100), TVA€ = TTC - HT
- Si HT et TVA% connus : TVA€ = HT * TVA%/100, TTC = HT + TVA€
- Si montant unique sans précision : considère-le comme TTC avec TVA 20%
- Arrondir à 2 décimales
- Pour la date : si absente, utilise la date fournie dans le message"""

CACHED_SYSTEM = [
    {
        "type": "text",
        "text": SYSTEM_PROMPT,
        "cache_control": {"type": "ephemeral"},
    }
]


def _extract_json(text: str) -> dict:
    text = re.sub(r"```(?:json)?\s*", "", text).strip().rstrip("`").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise ValueError(f"JSON introuvable dans : {text[:200]}")


def parse_expense_text(text: str, today: str) -> dict:
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=CACHED_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": f"Date d'aujourd'hui : {today}\n\nAnalyse cette dépense :\n{text}",
            }
        ],
    )
    return _extract_json(message.content[0].text)


def parse_expense_image(image_bytes: bytes, mime_type: str, today: str) -> dict:
    image_data = base64.standard_b64encode(image_bytes).decode("utf-8")
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=CACHED_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": image_data,
                        },
                    },
                    {
                        "type": "text",
                        "text": f"Date d'aujourd'hui : {today}\n\nAnalyse ce reçu et extrais les informations de dépense.",
                    },
                ],
            }
        ],
    )
    return _extract_json(message.content[0].text)
