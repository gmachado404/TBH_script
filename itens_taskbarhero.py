"""
Tabela de itens do TaskbarHero: cada TIPO tem um nome fixo por nível. Como o
NOME do item determina o NÍVEL (mesma peça em grades diferentes tem o MESMO
nível), derivamos o nível do nome — bem mais confiável que ler "Requires Lv.XX"
por OCR.

Uso:
    import itens_taskbarhero as it
    it.nivel_do_nome("Vengeance Sword")  -> 65
    it.tipo_do_nome("Vengeance Sword")   -> "Sword"
A busca normaliza (minúsculas, sem espaços/apóstrofos) p/ casar com o OCR
(ex.: "VengeanceSword", "Fighter'sHelmet").
"""

import re

# Dados crus: cada tipo -> "Lv1 Nome Lv5 Nome ..." (espaços são irrelevantes).
_RAW = {
    "Amulet": "Lv1 Copper Amulet Lv5 Bronze Amulet Lv10 Silver Amulet Lv15 Gold Amulet Lv20 Platinum Amulet Lv25 Crystal Amulet Lv30 Moonstone Pendant Lv35 Amber Pendant Lv40 Ruby Pendant Lv45 Amethyst Pendant Lv50 Emerald Amulet Lv55 Diamond Amulet Lv60 Stardust Amulet Lv65 Eclipse Amulet Lv70 Celestial Amulet Lv75 Astral Amulet Lv80 Ethereal Amulet Lv85 Void Amulet Lv90 Abyss Amulet",
    "Armor": "Lv1 Wooden Armor Lv5 Empire Armor Lv10 Iron Plate Lv15 Chain Mail Lv20 Knight's Armor Lv25 Fate Armor Lv30 War Armor Lv35 Heavy Armor Lv40 Rune Plate Lv45 Dragon Scale Armor Lv50 Mystic Armor Lv55 Great Armor Lv60 Ancient Armor Lv65 Shine Armor Lv70 Void Armor Lv75 Dragon Armor Lv80 Dimensional Armor Lv85 Shadow Armor Lv90 Eternal Armor Lv100 Radiant Armor",
    "Arrow": "Lv1 Wooden Arrow Lv5 Iron Arrow Lv10 Hunter's Arrow Lv15 Barbed Arrow Lv20 Azure Arrow Lv25 Brutal Arrow Lv30 Gale Arrow Lv35 Serpent Arrow Lv40 Rune Arrow Lv45 Tribal Arrow Lv50 Fate Arrow Lv55 Storm Arrow Lv60 Obsidian Arrow Lv65 Haste Arrow Lv70 Void Arrow Lv75 Poison Arrow Lv80 Dimensional Arrow Lv85 Shadow Arrow Lv90 Ancient Arrow Lv100 Exalted Arrow",
    "Axe": "Lv1 Wooden Axe Lv5 Iron Axe Lv10 Battle Axe Lv15 Steel Axe Lv20 War Axe Lv25 Knight's Axe Lv30 Great Axe Lv35 Heavy Axe Lv40 Rune Axe Lv45 Legend Axe Lv50 Fate Axe Lv55 Hero Axe Lv60 Storm Axe Lv65 Limitless Axe Lv70 Chaos Axe Lv75 Power Axe Lv80 Dimensional Axe Lv85 Shadow Axe Lv90 Eternal Axe Lv100 Radiant Axe",
    "Bolt": "Lv1 Short Bolt Lv5 Fear Bolt Lv10 Hunter's Bolt Lv15 Barbed Bolt Lv20 Beast Bolt Lv25 Swift Bolt Lv30 Iron Bolt Lv35 Heavy Bolt Lv40 Rune Bolt Lv45 Hero Bolt Lv50 Fate Bolt Lv55 Storm Bolt Lv60 Thunder Bolt Lv65 Haste Bolt Lv70 Void Bolt Lv75 Poison Bolt Lv80 Dimensional Bolt Lv85 Shadow Bolt Lv90 Ancient Bolt Lv100 Sanctified Bolt",
    "Boots": "Lv1 Wooden Boots Lv5 Empire Boots Lv10 Iron Boots Lv15 Knight Boots Lv20 Chain Boots Lv25 Fate Boots Lv30 War Boots Lv35 Heavy Boots Lv40 Rune Boots Lv45 Plate Boots Lv50 Mystic Boots Lv55 Great Boots Lv60 Ancient Boots Lv65 Shine Boots Lv70 Void Boots Lv75 Crystal Boots Lv80 Dimensional Boots Lv85 Shadow Boots Lv90 Eternal Boots Lv100 Radiant Boots",
    "Bow": "Lv1 Short Bow Lv5 Hunting Bow Lv10 Long Bow Lv15 Composite Bow Lv20 War Bow Lv25 Scarlet Bow Lv30 Dusk Bow Lv35 Jade Bow Lv40 Elite Bow Lv45 Rune Bow Lv50 Mystic Bow Lv55 Swift Bow Lv60 Ancient Bow Lv65 Limitless Bow Lv70 Chaos Bow Lv75 Storm Bow Lv80 Shadow Bow Lv85 Tempest Bow Lv90 Eternal Bow Lv100 Radiant Bow",
    "Bracer": "Lv1 Copper Bracer Lv5 Bronze Bracer Lv10 Silver Bracer Lv15 Gold Bracer Lv20 Platinum Bracer Lv25 Crystal Bracer Lv30 Obsidian Bracer Lv35 Shadow Bracer Lv40 Crimson Bracer Lv45 Bloodstone Bracer Lv50 Emerald Bracer Lv55 Diamond Bracer Lv60 Stardust Bracer Lv65 Eclipse Bracer Lv70 Celestial Bracer Lv75 Astral Bracer Lv80 Ethereal Bracer Lv85 Void Bracer Lv90 Abyss Bracer",
    "Crossbow": "Lv1 Short Crossbow Lv5 Leather Crossbow Lv10 Long Crossbow Lv15 Complete Crossbow Lv20 Exceptional Crossbow Lv25 Reinforced Crossbow Lv30 Iron Crossbow Lv35 Wing Crossbow Lv40 Elite Crossbow Lv45 Large Crossbow Lv50 Mystic Crossbow Lv55 Fast Crossbow Lv60 Ancient Crossbow Lv65 Limitless Crossbow Lv70 Chaos Crossbow Lv75 Power Crossbow Lv80 Dimensional Crossbow Lv85 Shadow Crossbow Lv90 Eternal Crossbow Lv100 Radiant Crossbow",
    "Earring": "Lv1 Copper Earring Lv5 Bronze Earring Lv10 Silver Earring Lv15 Gold Earring Lv20 Platinum Earring Lv25 Crystal Earring Lv30 Emerald Earring Lv35 Jade Earring Lv40 Tiger Eye Earring Lv45 Garnet Earring Lv50 Sapphire Earring Lv55 Diamond Earring Lv60 Moonstone Earring Lv65 Celestial Earring Lv70 Eclipse Earring Lv75 Astral Earring Lv80 Ethereal Earring Lv85 Void Earring Lv90 Abyss Earring",
    "Gloves": "Lv1 Leather Gloves Lv5 Empire Gloves Lv10 Iron Gloves Lv15 Knight Gloves Lv20 Chain Gloves Lv25 Fate Gloves Lv30 War Gloves Lv35 Heavy Gloves Lv40 Rune Gloves Lv45 Plate Gloves Lv50 Mystic Gloves Lv55 Great Gloves Lv60 Ancient Gloves Lv65 Shine Gloves Lv70 Void Gloves Lv75 Dragon Gloves Lv80 Dimensional Gloves Lv85 Shadow Gloves Lv90 Eternal Gloves Lv100 Radiant Gloves",
    "Hatchet": "Lv1 Short Hatchet Lv5 Leather Hatchet Lv10 Long Hatchet Lv15 Steel Hatchet Lv20 War Hatchet Lv25 Composite Hatchet Lv30 Battle Hatchet Lv35 Wing Hatchet Lv40 Elite Hatchet Lv45 Large Hatchet Lv50 Mystic Hatchet Lv55 Swift Hatchet Lv60 Ancient Hatchet Lv65 Limitless Hatchet Lv70 Chaos Hatchet Lv75 Power Hatchet Lv80 Dimensional Hatchet Lv85 Shadow Hatchet Lv90 Eternal Hatchet Lv100 Exalted Hatchet",
    "Helmet": "Lv1 Wooden Helmet Lv5 Empire Helmet Lv10 Iron Helmet Lv15 Knight Helmet Lv20 Chain Helmet Lv25 Medium Helmet Lv30 War Helmet Lv35 Emperor Helmet Lv40 Rune Helmet Lv45 Red Helmet Lv50 Fate Helmet Lv55 Great Helmet Lv60 Storm Helmet Lv65 Fighter's Helmet Lv70 Void Helmet Lv75 Crystal Helmet Lv80 Dimensional Helmet Lv85 Shadow Helmet Lv90 Eternal Helmet Lv100 Radiant Helmet",
    "Orb": "Lv1 Magic Orb Lv5 Elder Orb Lv10 Brilliant Orb Lv15 Frozen Orb Lv20 Prophecy Orb Lv25 Dark Orb Lv30 Rune Orb Lv35 Shining Orb Lv40 Arcane Orb Lv45 Fate Orb Lv50 Mystic Orb Lv55 Sky Orb Lv60 Spirit Orb Lv65 Ancient Orb Lv70 Abyssal Orb Lv75 Void Orb Lv80 Dimensional Orb Lv85 Shadow Orb Lv90 Eternal Orb Lv100 Aureate Orb",
    "Ring": "Lv1 Copper Ring Lv5 Bronze Ring Lv10 Silver Ring Lv15 Gold Ring Lv20 Platinum Ring Lv25 Crystal Ring Lv30 Amber Ring Lv35 Topaz Ring Lv40 Amethyst Ring Lv45 Garnet Ring Lv50 Emerald Ring Lv55 Diamond Ring Lv60 Moonstone Ring Lv65 Eclipse Ring Lv70 Celestial Ring Lv75 Astral Ring Lv80 Ethereal Ring Lv85 Void Ring Lv90 Abyss Ring",
    "Scepter": "Lv1 Novice Scepter Lv5 Iron Scepter Lv10 Blessed Scepter Lv15 Steel Scepter Lv20 Sacred Scepter Lv25 Bishop's Scepter Lv30 Devout Scepter Lv35 Heavy Scepter Lv40 Rune Scepter Lv45 Legend Scepter Lv50 Fate Scepter Lv55 Hero Scepter Lv60 Storm Scepter Lv65 Limitless Scepter Lv70 Chaos Scepter Lv75 Power Scepter Lv80 Dimensional Scepter Lv85 Shadow Scepter Lv90 Eternal Scepter Lv100 Radiant Scepter",
    "Shield": "Lv1 Buckler Lv5 Wooden Shield Lv10 Iron Shield Lv15 Heater Shield Lv20 Heavy Shield Lv25 Forest Shield Lv30 War Shield Lv35 Barrier Shield Lv40 Elite Shield Lv45 Crimson Shield Lv50 Mystic Shield Lv55 Grand Shield Lv60 Ancient Shield Lv65 Radiant Shield Lv70 Void Shield Lv75 Divine Shield Lv80 Dimensional Shield Lv85 Shadow Shield Lv90 Eternal Shield Lv100 Dragon Shield",
    "Staff": "Lv1 Wooden Staff Lv5 Herald Staff Lv10 Long Staff Lv15 Witch Staff Lv20 Azure Staff Lv25 Elder Staff Lv30 Sage Staff Lv35 Mystic Staff Lv40 Comet Staff Lv45 Crystal Staff Lv50 Void Staff Lv55 Conqueror Staff Lv60 Ancient Staff Lv65 Sacred Staff Lv70 Abyssal Staff Lv75 Chaos Staff Lv80 Tempest Staff Lv85 Nova Staff Lv90 Eternal Staff Lv100 Radiant Staff",
    "Sword": "Lv1 Long Sword Lv5 Cutlas Lv10 Rapier Lv15 Bastard Sword Lv20 Great Sword Lv25 Heavy Blade Lv30 Knight Sword Lv35 Commander's Sword Lv40 Rune Sword Lv45 Legend Sword Lv50 Fate Sword Lv55 Hero Sword Lv60 Storm Sword Lv65 Vengeance Sword Lv70 Void Blade Lv75 Crystal Blade Lv80 Dimensional Sword Lv85 Shadow Blade Lv90 Eternal Sword Lv100 Radiant Sword",
    "Tome": "Lv1 Prayer Tome Lv5 Empire Tome Lv10 Iron Tome Lv15 Knight's Tome Lv20 Blessed Tome Lv25 Commander's Tome Lv30 War Tome Lv35 Emperor's Tome Lv40 Rune Tome Lv45 Crimson Tome Lv50 Fate Tome Lv55 Grand Tome Lv60 Storm Tome Lv65 Warrior's Tome Lv70 Void Tome Lv75 Crystal Tome Lv80 Dimensional Tome Lv85 Shadow Tome Lv90 Eternal Tome Lv100 Empyrean Tome",
}


def _normalizar(nome):
    """Reduz o nome a só letras minúsculas (tira espaços, apóstrofos, dígitos)
    para casar com leituras do OCR (ex.: 'Fighter''s Helmet' -> 'fightershelmet')."""
    return re.sub(r"[^a-z]", "", (nome or "").lower())


def _construir():
    nivel, tipo = {}, {}
    for tp, raw in _RAW.items():
        for m in re.finditer(r"Lv(\d+)\s+([A-Za-z][A-Za-z' ]*?)(?=\s*Lv\d+|$)", raw):
            lv = int(m.group(1))
            chave = _normalizar(m.group(2))
            nivel[chave] = lv
            tipo[chave] = tp
    return nivel, tipo


NIVEL_POR_NOME, TIPO_POR_NOME = _construir()


def nivel_do_nome(nome):
    """Nível (int) do item pelo nome, ou None se não reconhecido."""
    return NIVEL_POR_NOME.get(_normalizar(nome))


def tipo_do_nome(nome):
    """Tipo (str, ex.: 'Sword') do item pelo nome, ou None."""
    return TIPO_POR_NOME.get(_normalizar(nome))


# ---------------------------------------------------------------------------
# MATERIAIS: o NOME determina grade E categoria (e portanto a stash). Não têm
# nível. Fonte: tabela do jogo (nome / grade / categoria / id).
# ---------------------------------------------------------------------------
ACESSORIO_TIPOS = {"Amulet", "Bracer", "Earring", "Ring"}

# categoria -> stash de destino (mapa do usuário). Offering ainda não mapeado.
CATEGORIA_STASH = {
    "Crafting": 2,
    "Decoration": 3,
    "Engraving": 4,
    "Inscription": 6,
    "Soul Stone": 6,     # soulstones movidos p/ o 6 (liberar o 7 p/ staging de síntese)
    "Offering": 6,       # moedas de aniversário vão junto das soulstones
}

# categoria -> grade -> [nomes]
_MATERIAIS = {
    "Decoration": {
        "common": ["Minor Ruby", "Minor Sapphire", "Minor Topaz", "Minor Emerald", "Minor Amethyst"],
        "uncommon": ["Obsidian Shard", "Coral Piece", "Jade Stone", "Amber Gem"],
        "rare": ["Ruby", "Sapphire", "Topaz", "Emerald", "Amethyst"],
        "legendary": ["Crystal Quartz", "Pearl", "Turquoise", "Garnet"],
        "immortal": ["Diamond", "Opal", "Lapis Lazuli", "Black Pearl"],
        "arcana": ["Arcane Crystal", "Mystic Topaz", "Enchanted Ruby", "Starlight Sapphire"],
        "beyond": ["Void Opal", "Astral Diamond", "Phantom Emerald", "Twilight Amethyst"],
        "celestial": ["Celestial Pearl", "Dragonite Crystal"],
        "divine": ["Void Crystal", "Abyssal Pearl"],
        "cosmic": ["Ethereal Gem", "Chaos Diamond"],
    },
    "Engraving": {
        "common": ["Goblin Hide", "Skeleton Bone", "Slime Jelly"],
        "uncommon": ["Wolf Fang", "Spider Silk", "Poisonous Herb", "Healing Herb"],
        "rare": ["Bat Wing Membrane", "Ogre Blood", "Mushroom Spore", "Ancient Tree Sap"],
        "legendary": ["Skull", "Harpy Feather", "Mandrake Root", "Nightshade Extract"],
        "immortal": ["Basilisk Scale", "Wyvern Claw", "Dice", "Demon Blood"],
        "arcana": ["Minotaur Horn", "Griffin Beak", "Phoenix Ash", "Dragon Bile"],
        "beyond": ["Wraith Essence", "Kraken Ink", "Titan Marrow", "Void Ichor"],
        "celestial": ["Abyssal Mucus", "Chaos Spore"],
        "divine": ["Primordial Sap", "Eldritch Venom"],
        "cosmic": ["Chaso Dice", "Void Tendril"],
    },
    "Inscription": {
        "common": ["Scroll of Common Inscription"],
        "uncommon": ["Scroll of Uncommon Inscription"],
        "rare": ["Scroll of Rare Inscription"],
        "legendary": ["Scroll of Legendary Inscription"],
        "immortal": ["Scroll of Immortal Inscription"],
        "arcana": ["Scroll of Arcana Inscription"],
        "beyond": ["Scroll of Beyond Inscription"],
        "celestial": ["Scroll of Celestial Inscription"],
        "divine": ["Scroll of Divine Inscription"],
        "cosmic": ["Scroll of Cosmic Inscription"],
    },
    "Crafting": {
        "common": ["Wood", "Stone", "Leather", "Copper Nugget"],
        "uncommon": ["Bronze Ingot", "Iron Ingot"],
        "rare": ["Silver Ingot", "Gold Ingot"],
        "legendary": ["Stardust Ingot", "Void Iron"],
        "immortal": ["Bloodstone", "Thunderstone"],
        "arcana": ["Chaos Shard", "Arcane Ore"],
        "beyond": ["Darksteel Ingot", "Orichalcum Ore"],
        "celestial": ["Moonstone", "Sunstone"],
        "divine": ["Mithril Ore", "Ethereal Ingot"],
        "cosmic": ["Adamantium Ore", "Aeon Ingot"],
    },
    "Offering": {
        "common": ["Kingdom 1st Anniversary Coin"],
        "uncommon": ["Empire 1st Anniversary Coin"],
        "rare": ["Kingdom 10th Anniversary Coin"],
        "legendary": ["Empire 10th Anniversary Coin"],
        "immortal": ["Kingdom 50th Anniversary Coin"],
        "arcana": ["Empire 50th Anniversary Coin"],
        "beyond": ["Kingdom 100th Anniversary Coin"],
        "celestial": ["Empire 100th Anniversary Coin"],
        "divine": ["Sacred Kingdom 1000th Anniversary Coin"],
        "cosmic": ["Eternal Empire 1000th Anniversary Coin"],
    },
    "Soul Stone": {
        "immortal": ["Soulstone - Normal"],
        "arcana": ["Soulstone - Nightmare"],
        "beyond": ["Soulstone - Hell"],
        "celestial": ["Soulstone - Torment"],
    },
}


def _construir_materiais():
    por_nome = {}
    for categoria, por_grade in _MATERIAIS.items():
        stash = CATEGORIA_STASH.get(categoria)
        for grade, nomes in por_grade.items():
            for nome in nomes:
                por_nome[_normalizar(nome)] = (grade, categoria, stash)
    return por_nome


MATERIAL_POR_NOME = _construir_materiais()


def material_info(nome):
    """(grade, categoria, stash) do material pelo nome, ou None se não é material
    conhecido. Materiais têm grade e categoria FIXOS pelo nome (sem nível)."""
    return MATERIAL_POR_NOME.get(_normalizar(nome))


def stash_do_equip(nome):
    """Stash de um equipamento conhecido (5 p/ acessório, 1 p/ resto), ou None."""
    tp = tipo_do_nome(nome)
    if tp is None:
        return None
    return 5 if tp in ACESSORIO_TIPOS else 1
