from datetime import date, timedelta


def calculate_sm2(card: dict, quality: int) -> dict:
    """
    SM-2 spaced repetition algorithm.
    quality: 0=raté, 2=difficile, 3=bien, 4=facile
    """
    ef = card.get("easiness_factor", 2.5)
    interval = card.get("interval", 1)
    repetitions = card.get("repetitions", 0)

    if quality < 3:
        repetitions = 0
        interval = 1
    else:
        if repetitions == 0:
            interval = 1
        elif repetitions == 1:
            interval = 6
        else:
            interval = round(interval * ef)
        repetitions += 1

    ef = max(1.3, ef + 0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))

    return {
        **card,
        "easiness_factor": round(ef, 2),
        "interval": interval,
        "repetitions": repetitions,
        "next_review": (date.today() + timedelta(days=interval)).isoformat(),
    }
