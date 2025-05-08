def get_nearest_levels(current_price, advanced_mode=False):
    # Ako cena nije validna, vrati podrazumevane vrednosti
    if not current_price or current_price <= 0:
        return 0.01862, 0.01868

    # Pronađi osnovni nivo (zaokruži na najbliži x.xxxx0)
    base = round(current_price * 10000) / 10000  # Zaokruživanje na 4 decimale
    base = (int(base * 100000) // 10) / 10000  # Zaokruživanje na x.xxxx0

    # Generiši nivoe
    step = 0.00005  # Smanjujemo korak na 5 pipova umesto 10
    historical_levels = []
    start_level = int(base * 10000) - (int(base * 10000) % 10)  # Počinjemo od x.xxxx0

    if advanced_mode:
        # Adaptivne zone: donja (1,2,3), gornja (7,8,9)
        for i in range(-5, 6):  # Smanjujemo raspon na ±5 nivoa
            level = (start_level + i * 5) / 10000  # Nivo na x.xxxx0 (korak od 5 pipova)
            for offset in [0.00001, 0.00002, 0.00003, 0.00007, 0.00008, 0.00009]:
                historical_levels.append(level + offset)
    else:
        # Standardni nivoi: x.xxxx2 i x.xxxx8
        for i in range(-5, 6):  # Smanjujemo raspon na ±5 nivoa
            level = (start_level + i * 5) / 10000  # Nivo na x.xxxx0 (korak od 5 pipova)
            level_2 = level + 0.00002  # x.xxxx2
            level_8 = level + 0.00008  # x.xxxx8
            historical_levels.extend([level_2, level_8])

    # Sortiraj nivoe
    historical_levels.sort()

    # Pronađi najbliže nivoe
    support = max([level for level in historical_levels if level < current_price], default=historical_levels[0])
    resistance = min([level for level in historical_levels if level > current_price], default=historical_levels[-1])

    return support, resistance