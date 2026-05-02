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

Retourne UNIQUEMENT ce JSON (null si information indisponible, pas de markdown, pas d'explication) :
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
- Si montant unique sans précision dans un contexte français clairement taxé : considère-le comme TTC avec TVA 20%
- Si la TVA n'est pas détectable (reçu étranger, auto-entrepreneur, franchise de TVA, mention "TVA non applicable") : utilise null pour tva_pct et tva_eur, et null pour ht si seul le TTC est connu
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


_TEXT_ONLY_RULES = (
    "RÈGLES POUR CE MESSAGE TEXTE (sans reçu physique) :\n"
    "- tva_pct et tva_eur : toujours null (aucun reçu = TVA non vérifiable)\n"
    "- ht : null sauf si le message contient explicitement 'HT' ou 'hors taxe'\n"
    "- ttc : null sauf si le message contient explicitement un montant chiffré (ex: 25€, 18.50)\n"
    "- Ne calcule aucune valeur dérivée, retourne uniquement ce qui est écrit\n"
    "- marchand : extraire UNIQUEMENT le nom du lieu/marchand, en ignorant les montants et les dates.\n"
    "  Si un nom propre est présent, l'utiliser en priorité (ex: 'déjeuner Paul' → 'Paul').\n"
    "  Sinon, combiner le type de dépense et le lieu (ex: 'taxi aéroport' → 'Taxi Aéroport').\n"
    "  Si aucun nom identifiable : retourner null.\n"
    "  Exemples : '15€ café réunion 02/05' → 'Café Réunion' | '50€ taxi aéroport 15/05' → 'Taxi Aéroport' | '25€ déjeuner Paul 01/05' → 'Paul'\n\n"
)


def parse_expense_text(text: str, today: str) -> dict:
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=512,
        system=CACHED_SYSTEM,
        messages=[
            {
                "role": "user",
                "content": f"Date d'aujourd'hui : {today}\n\n{_TEXT_ONLY_RULES}Analyse cette dépense :\n{text}",
            }
        ],
    )
    expense = _extract_json(message.content[0].text)

    # Safety net: always null TVA for text-only entries
    expense["tva_pct"] = None
    expense["tva_eur"] = None

    # Fallback: use the raw message as merchant name if none was detected
    marchand = expense.get("marchand")
    if not marchand or marchand in ("N/A", "Inconnu", "inconnu", "unknown", "Non précisé"):
        expense["marchand"] = text.strip()

    expense["remarques"] = "pas de ticket dispo"
    return expense


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
    expense = _extract_json(message.content[0].text)
    expense["remarques"] = ""
    return expense
