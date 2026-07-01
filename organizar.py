"""
Organização do inventário do TaskbarHero — ETAPA 2.

Pega os itens do baú (grade 2x7 abaixo do painel HERO), descobre o TIPO de cada
um (pelo nome e pelas TAGS do tooltip) e leva para a STASH (aba) correspondente,
clicando-pega no baú e clicando-solta num slot vazio da aba. A cada 5 itens
colocados, aperta o botão de organização automática do jogo.

Reaproveita toda a detecção do inventario.py (captura só da janela, leitura por
hover, etc.).

Mapa de destino (definido pelo usuário):
  Stash 1: Equipamentos (armas + armaduras)
  Stash 2: tag "Crafting Material"
  Stash 3: tag "Decoration Material"   (NÃO confundir com "Decoration Slot")
  Stash 4: tag "Engraving Material"
  Stash 5: Acessórios (Earring/Ring/Bracer/Amulet/Pendant)
  Stash 6: Inscription + Soulstones + Offerings (não sintetizáveis)
  Stash 7: STAGING de síntese (consolidar itens p/ completar 9 — ver síntese)

Modos:
  python organizar.py ler        # DRY-RUN: lê o baú, classifica e imprime. NÃO move.
  python organizar.py abas       # testa: clica em cada aba 1..7 (visual)
  python organizar.py mover 1    # MOVE só 1 item (teste seguro). 'mover N' = N itens.
  python organizar.py mover      # MOVE tudo: esvazia o baú roteando por tipo.
"""

import json
import re
import sys
import time
from collections import Counter

import inventario as inv
import itens_taskbarhero as ith
import mercado
import parada

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO
# ---------------------------------------------------------------------------
# Onde o painel de info aparece ao passar o mouse na grade do BAÚ. O painel sai
# no MESMO Y dos itens do STASH (não no nível do baú), então usamos GRADE_Y.
BAU_REF_Y = inv.GRADE_Y
# Janela X (larga) onde o painel de info do baú aparece. O painel não acompanha
# o slot e, para itens equipáveis, surge um 2º tooltip (o EQUIPADO) ao lado. Não
# dá para excluí-lo só pela janela (a posição varia com a coluna do slot). Em vez
# disso, ler_item_por_hover separa os dois tooltips e escolhe o nome mais perto
# do X do slot mirado. Aqui só garantimos uma janela larga o bastante.
BAU_NOME_X = (inv.BAU_X - 150, inv.BAU_X + 300)   # ~ (681, 1131)

# Botões das 7 abas da STASH (centro de cada um). Calibre com 'main.py pos'.
ABAS_Y = 420
ABAS_X = [522, 563, 605, 646, 687, 729, 770]  # abas 1..7

# Botão de organização automática do STASH (compacta a aba de destino).
BOTAO_ORGANIZAR = (775, 755)
ORGANIZAR_A_CADA = 5          # aperta o botão a cada N itens colocados

# Botão "sort" do BAÚ: compacta o baú e traz os itens escondidos (a tela rola)
# para a janela 2x7 visível. Apertado a cada N itens movidos do baú.
BOTAO_SORT_BAU = (945, 702)
SORTEAR_BAU_A_CADA = 10

LIMITE_PASSADAS = 30          # segurança: máx. de ciclos scan->mover->sort

# --- Loop autônomo ---------------------------------------------------------
INTERVALO_LOOP_MIN = 30        # minutos entre ciclos de organização
ICONE_BARRA = (30, 480)        # ícone do jogo na barra de tarefas (reabrir/focar)

PAUSA_CLIQUE = 0.15           # s após cada clique
PAUSA_TROCA_ABA = 0.70        # s após trocar de aba (deixa a grade atualizar)
PAUSA_PEGA_SOLTA = 0.20       # s entre pegar e soltar o item

# --- Cubo / Synthesis ------------------------------------------------------
# Grade 3x3 do cubo (mesmo passo/tamanho do baú e stash). Canto sup-esq do
# slot (0,0). O resultado da síntese aparece no slot do MEIO (1,1) == "2,2".
CUBO_X = 1230
CUBO_Y = 481
CUBO_LINHAS = 3
CUBO_COLUNAS = 3
BOTAO_SYNTH = (1360, 640)     # botão "Synthesize"
# Popup de confirmação após Synthesize (se houver). None = sem popup.
CONFIRM_SYNTH = None

# Dropdown de MODO do cubo (Synthesis / Alchemy / ...). Abre e clica a opção.
CUBO_MODO_DROPDOWN = (1245, 415)
CUBO_MODO_SYNTHESIS = (1237, 442)   # centro da opção "Synthesis"
CUBO_MODO_ALCHEMY = (1237, 468)     # centro da opção "Alchemy" (referência)
# Dropdown de TIPO (Equipment / Material / Accessories).
CUBO_TIPO_DROPDOWN = (1295, 640)
CUBO_TIPO_EQUIPAMENTO = (1242, 672)   # centro (1177..1307, 660..684)
CUBO_TIPO_MATERIAL = (1242, 698)      # centro (1177..1307, 686..710)
CUBO_TIPO_ACESSORIO = None            # ainda não calibrado
# Dropdown de FAIXA DE NÍVEL (só no Synthesis de EQUIPAMENTO). 8 tiers.
CUBO_NIVEL_DROPDOWN = (1375, 415)
# (limite_inferior, (x, y) do centro da opção). Tiers empilham 27px; x≈1376.
# Regra: item de nível L usa o tier de MAIOR limite_inferior <= L (item na borda
# de baixo -> síntese gera itens de nível mais alto). Materiais não usam tier.
NIVEL_TIERS = [
    (1,  (1376, 442)),   # Lv 1~10
    (10, (1376, 469)),   # Lv 10~20
    (15, (1376, 496)),   # Lv 15~30
    (20, (1376, 523)),   # Lv 20~40
    (30, (1376, 550)),   # Lv 30~50
    (40, (1376, 577)),   # Lv 40~65
    (50, (1376, 604)),   # Lv 50~65
    (65, (1376, 631)),   # Lv 65~80
]
# Ordem dos grades, do MENOR para o MAIOR (TaskbarHero). Síntese funde 9 de um
# grade no próximo. Preferimos sintetizar o grade mais BAIXO (menos valioso).
GRADES = ("common", "uncommon", "rare", "legendary", "immortal",
          "arcana", "beyond", "celestial", "divine", "cosmic")
SYNTH_QTD = 9                 # itens consumidos por síntese
ARQUIVO_DB = "inventario_db.json"
STASH_STAGING = 7             # stash usada p/ consolidar fodder de síntese (cross)
FALTAR_MAX = 4               # cross-synth só se faltar <= isso p/ completar 9
# Categorias de MATERIAL que podem ser sintetizadas (fundem por grade). Soul
# Stone, Inscription e Offering NÃO fundem.
CATEGORIAS_SINTETIZAVEIS = ("Crafting", "Decoration", "Engraving")

# --- Classificação ---------------------------------------------------------
ACESSORIOS = ("earring", "ring", "bracer", "amulet", "pendant", "necklace")
# (frase-da-tag-sem-espaços, stash). Procuradas no texto do tooltip.
TAGS_STASH = (
    ("craftingmaterial", 2),
    ("decorationmaterial", 3),
    ("engravingmaterial", 4),
    ("inscriptionmaterial", 6),
)
# ---------------------------------------------------------------------------


def classificar(nome, linhas):
    """Decide para qual STASH (1..7) o item vai. None = não reconhecido."""
    nome_l = nome.lower()
    nome_sem = nome_l.replace(" ", "")
    texto = " ".join(t for _topo, _x1, _x2, t in linhas).lower()
    texto_sem = texto.replace(" ", "")

    # Soulstone (robusto a corte do OCR: "Soulstone"->"ulstone"/"Soustone-").
    # "stone-" pega "Soulstone-Hell/Nightmare"; exclui "Moonstone Pendant".
    if "ulstone" in nome_sem or "stone-" in nome_sem:
        return 6
    for tag, stash in TAGS_STASH:
        if tag in texto_sem:
            return stash
    if any(a in nome_sem for a in ACESSORIOS):
        return 5
    if "grade" in texto:          # tem raridade -> é equipamento (arma/armadura)
        return 1
    return None


def _centro_x(ln):
    return (ln[1] + ln[2]) / 2


def grade_nivel(linhas, cx):
    """Extrai (grade, nivel) do tooltip do item MIRADO (o mais perto de cx em X,
    para ignorar o tooltip do item equipado). grade = uma das GRADES (minúscula)
    ou None; nivel = int do 'Requires Lv.XX' alinhado ao grade, ou None."""
    grades_ln = [ln for ln in linhas if "grade" in ln[3].lower()]
    grade, gcx = None, None
    if grades_ln:
        gl = min(grades_ln, key=lambda ln: abs(_centro_x(ln) - cx))
        gcx = _centro_x(gl)
        txt = gl[3].lower().replace(" ", "")
        achados = [g for g in GRADES if g in txt]
        if achados:
            grade = max(achados, key=len)   # 'uncommon' vence 'common' (substring)

    nivel = None
    cands = [ln for ln in linhas if "lv" in ln[3].lower()]
    if gcx is not None:                      # nível do MESMO tooltip (X alinhado)
        cands = [ln for ln in cands if abs(_centro_x(ln) - gcx) <= 120] or cands
    for ln in cands:
        m = re.search(r"lv\.?\s*(\d+)", ln[3].lower())
        if m:
            nivel = int(m.group(1))
            break
    return grade, nivel


def classificar_completo(nome, linhas, cx):
    """Devolve (stash, grade, nivel) priorizando as TABELAS do jogo
    (determinístico pelo NOME); OCR/tags só quando o nome não é reconhecido.
      - Material: nome -> grade + categoria(stash); sem nível.
      - Equipamento: nome -> nível + tipo(stash); grade vem do OCR (varia/peça).
      - Desconhecido: classify por tag + grade/nivel por OCR."""
    grade_ocr, nivel_ocr = grade_nivel(linhas, cx)
    mat = ith.material_info(nome)
    if mat:
        grade, _cat, stash = mat
        return stash, grade, None
    stash_eq = ith.stash_do_equip(nome)
    if stash_eq is not None:
        return stash_eq, grade_ocr, ith.nivel_do_nome(nome)
    return classificar(nome, linhas), grade_ocr, nivel_ocr


# --- Leitura do baú --------------------------------------------------------
def ler_bau(salvar_debug=True):
    """Lê todos os slots do baú 2x7. Devolve lista de dicts com r, c, nome,
    stash e linhas. Slots vazios são ignorados."""
    itens = []
    n = 0
    total = inv.BAU_LINHAS * inv.BAU_COLUNAS
    # SORT do baú ANTES de ler: compacta, ordena e revela itens escondidos
    # (stacks), evitando leituras inconsistentes/duplicadas.
    sortear_bau()
    # captura inicial (mouse fora) para saber quais slots estão ocupados —
    # assim não passamos o mouse em slot vazio (evita ler lixo do HERO).
    inv.deslizar_mouse(*inv.ponto_descanso())
    time.sleep(inv.ATRASO_HOVER)
    tela = inv.capturar_tela()
    for r in range(inv.BAU_LINHAS):
        for c in range(inv.BAU_COLUNAS):
            n += 1
            if inv.slot_vazio(tela, r, c, inv.BAU_X, inv.BAU_Y):
                print(f"  [{n}/{total}] baú ({r},{c}) -> (vazio)", flush=True)
                continue
            nome, linhas = inv.ler_item_por_hover(
                r, c, gx=inv.BAU_X, gy=inv.BAU_Y, ref_y=BAU_REF_Y,
                faixa_x=BAU_NOME_X, base=tela,
                salvar_debug=salvar_debug, prefixo_debug="bau")
            if not nome:
                print(f"  [{n}/{total}] baú ({r},{c}) -> (sem leitura)", flush=True)
                continue
            cx, _cy = inv.slot_centro(r, c, inv.BAU_X, inv.BAU_Y)
            stash, grade, nivel = classificar_completo(nome, linhas, cx)
            itens.append({"r": r, "c": c, "nome": nome, "grade": grade,
                          "nivel": nivel, "stash": stash, "linhas": linhas})
            destino = f"Stash {stash}" if stash else "??? (não reconhecido)"
            extra = f"  [{grade or '?'} Lv.{nivel if nivel is not None else '?'}]"
            print(f"  [{n}/{total}] baú ({r},{c}) -> {nome!r}{extra}  =>  {destino}",
                  flush=True)
    inv.mover_mouse(*inv.ponto_descanso())
    return itens


# --- Escaneamento das stashes (store de itens) -----------------------------
def ler_stash_aba(stash, salvar_debug=False):
    """Vai para a aba 'stash' e lê todos os slots OCUPADOS (nome, grade, nivel).
    Devolve lista de dicts {stash, r, c, nome, grade, nivel}."""
    if not garantir_aba(stash):
        print(f"  Stash {stash}: aba não ativou — pulando", flush=True)
        return []
    inv.deslizar_mouse(*inv.ponto_descanso())
    time.sleep(inv.ATRASO_HOVER)
    tela = inv.capturar_tela()
    itens = []
    for r in range(inv.LINHAS):
        for c in range(inv.COLUNAS):
            if inv.slot_vazio(tela, r, c):
                continue
            nome, linhas = inv.ler_item_por_hover(
                r, c, base=tela,
                salvar_debug=salvar_debug, prefixo_debug=f"stash{stash}")
            cx, _cy = inv.slot_centro(r, c)
            _dest, grade, nivel = classificar_completo(nome, linhas, cx)
            itens.append({"stash": stash, "r": r, "c": c, "nome": nome,
                          "grade": grade, "nivel": nivel})
            print(f"    ({r},{c}) {nome!r}  grade={grade} nivel={nivel}",
                  flush=True)
    return itens


def grupos_sintetizaveis(itens):
    """Conta itens pela CHAVE DE SÍNTESE (material: categoria+grade; equipamento:
    stash+grade+nível) e devolve os grupos com >= SYNTH_QTD, do grade mais BAIXO
    para o mais alto. Materiais NÃO têm nível — agrupam só por grade+categoria."""
    cont = Counter()
    for it in itens:
        k = chave_sintese(it)
        if k:
            cont[k] += 1
    ordem = {g: i for i, g in enumerate(GRADES)}
    grupos = [(k, q) for k, q in cont.items() if q >= SYNTH_QTD]
    grupos.sort(key=lambda kv: ordem.get(_grade_da_chave(kv[0]), 99))
    return cont, grupos


def relatorio_grupos(itens):
    cont, grupos = grupos_sintetizaveis(itens)
    ordem = {g: i for i, g in enumerate(GRADES)}
    print("\nGrupos de síntese -> qtd:")
    for k, q in sorted(cont.items(),
                       key=lambda kv: (str(kv[0][1]),
                                       ordem.get(_grade_da_chave(kv[0]), 99))):
        marca = "   <= SINTETIZÁVEL (>=9)" if q >= SYNTH_QTD else ""
        print(f"  {_descr_chave(k)}: {q}{marca}", flush=True)
    print(f"\n{len(grupos)} grupo(s) prontos para síntese.")


def escanear_stashs(salvar_debug=False, salvar_json=True):
    """Escaneia as 7 stashes, monta o store de itens e mostra os grupos."""
    print("Escaneando as 7 stashes (nome, grade, nível). NÃO mexa no mouse.")
    print("Começando em 5s...\n")
    for s in range(5, 0, -1):
        print(f"  {s}...", end="\r", flush=True)
        time.sleep(1)
    print("Iniciado!        \n")

    base, todos = {}, []
    t0 = time.time()
    for s in range(1, 8):
        print(f"  Stash {s}:", flush=True)
        itens = ler_stash_aba(s, salvar_debug)
        base[str(s)] = itens
        todos.extend(itens)
    inv.mover_mouse(*inv.ponto_descanso())
    dt = time.time() - t0
    por_item = (dt / len(todos) * 1000) if todos else 0
    print(f"\n-> {dt:.1f}s no total, {por_item:.0f} ms/item lido", flush=True)

    if salvar_json:
        with open(ARQUIVO_DB, "w", encoding="utf-8") as f:
            json.dump(base, f, ensure_ascii=False, indent=2)
        print(f"\n-> store salvo em {ARQUIVO_DB}")
    print(f"-> {len(todos)} itens lidos nas 7 stashes.")
    relatorio_grupos(todos)
    return base


# --- Cliques (movimento) ---------------------------------------------------
def clicar(x, y):
    """Move até (x, y) com movimento real e clica (botão esquerdo). Dá um respiro
    p/ o cursor assentar antes de apertar e um gap press->release — sem isso o
    jogo às vezes ignora o clique (pick/place perdido)."""
    inv.deslizar_mouse(x, y)
    time.sleep(0.02)
    inv.xtest.fake_input(inv._display, inv.X.ButtonPress, 1)
    inv._display.sync()
    time.sleep(0.02)
    inv.xtest.fake_input(inv._display, inv.X.ButtonRelease, 1)
    inv._display.sync()
    time.sleep(PAUSA_CLIQUE)


def aba_ativa(tela):
    """Detecta qual aba (1..7) está SELECIONADA. A aba ativa fica mais clara/
    destacada que as outras, então pegamos a de maior brilho médio. Devolve
    1..7 ou None."""
    melhor, melhor_b = None, -1.0
    for i, x in enumerate(ABAS_X):
        regiao = tela[ABAS_Y - 10:ABAS_Y + 10, x - 14:x + 14]
        if regiao.size == 0:
            continue
        b = float(regiao.mean())
        if b > melhor_b:
            melhor_b, melhor = b, i + 1
    return melhor


def _clicar_aba(stash):
    """Só clica no botão da aba (sem verificar)."""
    clicar(ABAS_X[stash - 1], ABAS_Y)
    time.sleep(PAUSA_TROCA_ABA)


def trocar_aba(stash):
    """Clica na aba e CONFIRMA que ela ficou ativa (o clique às vezes não
    registra). Tenta até 3x. Devolve True se a aba certa está ativa."""
    ativa = None
    for tentativa in range(3):
        _clicar_aba(stash)
        inv.deslizar_mouse(*inv.ponto_descanso())
        time.sleep(inv.ATRASO_HOVER)
        ativa = aba_ativa(inv.capturar_tela())
        if ativa == stash:
            return True
        print(f"    (aba {stash} não ativou — detectada={ativa}, "
              f"retry {tentativa + 1}/3)", flush=True)
    print(f"    AVISO: não consegui ativar a aba {stash} (ativa={ativa})",
          flush=True)
    return False


def organizar_automatico():
    """Aperta o botão de organização automática do STASH (aba atual)."""
    clicar(*BOTAO_ORGANIZAR)
    time.sleep(PAUSA_TROCA_ABA)


def sortear_bau():
    """Aperta o 'sort' do baú: compacta e traz itens escondidos para a vista."""
    clicar(*BOTAO_SORT_BAU)
    time.sleep(PAUSA_TROCA_ABA)


def pegar_e_soltar(origem, destino):
    """Clica-pega na origem e clica-solta no destino (click-pick/click-place)."""
    clicar(*origem)   # pega o item (fica no cursor)
    time.sleep(PAUSA_PEGA_SOLTA)
    clicar(*destino)  # solta no slot vazio
    time.sleep(PAUSA_PEGA_SOLTA)


def _mover_verificado(origem, destino, vazio):
    """Pega em origem, solta em destino e CONFIRMA que o slot 'vazio' do STASH
    ficou ocupado. Lida com clique perdido: re-solta (caso o item tenha ficado no
    cursor) e, se mesmo assim falhar (o PICK caiu), repete o ciclo. Como um pick
    que falha NÃO recompacta o baú, repetir o pega+solta é seguro. True se colocou."""
    for _ in range(2):
        pegar_e_soltar(origem, destino)
        if _stash_dest_ocupado(vazio):
            return True
        clicar(*destino)               # o place pode ter caído (item no cursor)
        time.sleep(PAUSA_PEGA_SOLTA)
        if _stash_dest_ocupado(vazio):
            return True
    return False


def achar_slot_vazio_stash():
    """Com o mouse fora, captura a aba atual e devolve (linha, coluna) do 1º slot
    VAZIO do STASH (ordem: esquerda->direita, cima->baixo). None se cheio."""
    inv.deslizar_mouse(*inv.ponto_descanso())
    time.sleep(inv.ATRASO_HOVER)
    tela = inv.capturar_tela()
    for r in range(inv.LINHAS):
        for c in range(inv.COLUNAS):
            if inv.slot_vazio(tela, r, c):
                return r, c
    return None


def _stash_dest_ocupado(vazio):
    """True se o slot 'vazio' do STASH agora está OCUPADO (item foi colocado).
    Verifica o DESTINO, não a origem: o baú recompacta ao remover um item, então
    o slot de origem nunca fica vazio e não serve de prova de que o move deu certo."""
    inv.deslizar_mouse(*inv.ponto_descanso())
    time.sleep(inv.ATRASO_HOVER)
    return not inv.slot_vazio(inv.capturar_tela(), vazio[0], vazio[1])


# --- Cache da ABA ativa (evita trocar_aba redundante) ----------------------
_aba_atual = None


def garantir_aba(stash):
    """Como trocar_aba, mas PULA se a aba já está ativa (cache). Só a função
    trocar_aba muda a aba ativa do STASH, então o cache é confiável."""
    global _aba_atual
    if _aba_atual == stash:
        return True
    if trocar_aba(stash):
        _aba_atual = stash
        return True
    _aba_atual = None
    return False


# --- Modelo em memória das stashes (evita re-ler 49 hovers a cada síntese) --
# _modelo[s] = lista de itens {nome,grade,nivel} na ORDEM DOS SLOTS (slot i ->
# modelo[i]; pos = (i//COLUNAS, i%COLUNAS)). Mantemos a stash COMPACTADA: adds
# vão pro fim; após síntese pressionamos organizar (compacta+ordena) e re-
# ordenamos o modelo igual (grade desc, nome asc). Self-heal: em falha, invalida.
_modelo = {}


def _rank_grade(g):
    try:
        return GRADES.index(g)
    except (ValueError, TypeError):
        return -1


# Ordem dos TIPOS de equipamento pelo ID-base do jogo (GEAR table). O sort do
# jogo dentro de um grade é por ID asc == (rank do tipo, nível).
TIPO_RANK = {
    "Sword": 0, "Bow": 1, "Staff": 2, "Scepter": 3, "Crossbow": 4, "Axe": 5,
    "Shield": 6, "Arrow": 7, "Orb": 8, "Tome": 9, "Bolt": 10, "Hatchet": 11,
    "Helmet": 12, "Armor": 13, "Gloves": 14, "Boots": 15,
    "Amulet": 16, "Earring": 17, "Ring": 18, "Bracer": 19,
}


# Faixa de ID por categoria de MATERIAL (11xxxx..19xxxx) — sempre ANTES de
# equipamento (ID 3xxxxx+). Dentro de uma stash só há 1 categoria, então a ordem
# entre materiais do mesmo grade não importa (qualquer 9 fundem).
_CAT_RANK = {"Decoration": 11, "Engraving": 12, "Inscription": 13,
             "Crafting": 14, "Offering": 16, "Soul Stone": 19}


def _ordem_sort(it):
    """Ordem do SORT do jogo: grade DESC, depois ID do item ASC. ID ~ material
    (11x-19x) vem ANTES de equipamento (3xx-6xx, = 30+rank do tipo, depois nível).
    Desconhecido (OCR ruidoso) vai pro fim do grade."""
    nome = it.get("nome") or ""
    g = -_rank_grade(it.get("grade"))
    mat = ith.material_info(nome)
    if mat:
        return (g, _CAT_RANK.get(mat[1], 15), 0)
    tr = TIPO_RANK.get(ith.tipo_do_nome(nome))
    if tr is not None:
        return (g, 30 + tr, ith.nivel_do_nome(nome) or 0)
    return (g, 99, 0)


def _item_min(it):
    return {"nome": it.get("nome"), "grade": it.get("grade"), "nivel": it.get("nivel")}


def modelo_invalidar(stash=None):
    if stash is None:
        _modelo.clear()
    else:
        _modelo.pop(stash, None)


def modelo_stash(stash):
    """Modelo da stash (itens em ordem de slot). Lê do jogo só na 1ª vez (ou após
    invalidar): ordena e pressiona organizar p/ as posições casarem com o modelo."""
    if _modelo.get(stash) is None:
        if not garantir_aba(stash):
            return []
        itens = [_item_min(x) for x in ler_stash_aba(stash)]
        itens.sort(key=_ordem_sort)
        organizar_automatico()          # compacta+ordena no jogo (= ao modelo)
        _modelo[stash] = itens
    return _modelo[stash]


def modelo_proximo_vazio(stash):
    """(r,c) do 1º slot vazio (a stash fica compactada), ou None se cheia."""
    n = len(modelo_stash(stash))
    if n >= inv.LINHAS * inv.COLUNAS:
        return None
    return (n // inv.COLUNAS, n % inv.COLUNAS)


def modelo_add(stash, it):
    modelo_stash(stash).append(_item_min(it))


def modelo_remove(stash, itens):
    alvo = _modelo.get(stash)
    if alvo is None:
        return
    for it in itens:
        for i, x in enumerate(alvo):
            if (x["nome"] == it.get("nome") and x["grade"] == it.get("grade")
                    and x["nivel"] == it.get("nivel")):
                alvo.pop(i)
                break


def modelo_com_pos(stash):
    """[(item, r, c)] do modelo, com a posição derivada do índice no slot."""
    return [(it, i // inv.COLUNAS, i % inv.COLUNAS)
            for i, it in enumerate(modelo_stash(stash))]


def _compactar_modelo(stash):
    """Após a síntese tirar itens da stash: organiza no jogo (compacta+ordena) e
    re-ordena o modelo igual, p/ as posições voltarem a casar."""
    if not garantir_aba(stash):
        modelo_invalidar(stash)
        return
    organizar_automatico()
    if _modelo.get(stash) is not None:
        _modelo[stash].sort(key=_ordem_sort)


# --- Síntese (cubo) --------------------------------------------------------
def _cubo_slots():
    """Centros dos 9 slots do cubo 3x3 (ordem L->R, cima->baixo)."""
    return [inv.slot_centro(r, c, CUBO_X, CUBO_Y)
            for r in range(CUBO_LINHAS) for c in range(CUBO_COLUNAS)]


def _esperar_sintese(timeout=10.0):
    """Espera a síntese CONCLUIR: os 8 slots AO REDOR do centro (1,1) ficam
    VAZIOS (os 9 itens foram consumidos; só o resultado fica no centro). Usa
    slot_vazio (brilho). Devolve True quando esvaziaram, False no timeout."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        inv.deslizar_mouse(*inv.ponto_descanso())
        time.sleep(inv.ATRASO_HOVER)
        tela = inv.capturar_tela()
        ao_redor_vazio = all(
            inv.slot_vazio(tela, r, c, CUBO_X, CUBO_Y)
            for r in range(CUBO_LINHAS) for c in range(CUBO_COLUNAS)
            if not (r == 1 and c == 1))
        if ao_redor_vazio:
            return True
        time.sleep(0.2)
    return False


def bau_tem_vaga():
    """True se há ao menos 1 slot vazio no baú (p/ receber o resultado da síntese)."""
    inv.deslizar_mouse(*inv.ponto_descanso())
    time.sleep(inv.ATRASO_HOVER)
    tela = inv.capturar_tela()
    for r in range(inv.BAU_LINHAS):
        for c in range(inv.BAU_COLUNAS):
            if inv.slot_vazio(tela, r, c, inv.BAU_X, inv.BAU_Y):
                return True
    return False


def _setar_dropdown(header, opcao, regiao, marcador):
    """Abre o dropdown (clica no header), clica a 'opcao' e, se a lista continuar
    ABERTA (sinal: 'marcador' ainda aparece em 'regiao'), fecha clicando no
    header. Os dropdowns do cubo são toggle: clicar na opção JÁ ATIVA não fecha a
    lista — então precisamos detectar e fechar pelo header."""
    clicar(*header)
    time.sleep(PAUSA_CLIQUE)
    clicar(*opcao)
    time.sleep(PAUSA_CLIQUE)
    if marcador in inv.ocr_regiao(*regiao).lower():   # lista ainda aberta
        clicar(*header)
        time.sleep(PAUSA_CLIQUE)


def selecionar_modo_synthesis():
    """Garante o modo 'Synthesis' (lista mostra 'Alchemy' quando aberta)."""
    _setar_dropdown(CUBO_MODO_DROPDOWN, CUBO_MODO_SYNTHESIS,
                    (1169, 428, 1305, 500), "alchemy")


def selecionar_tipo(chave):
    """Abre o dropdown de tipo e escolhe Equipment/Material/Accessories conforme
    a chave. False se o tipo não está calibrado (ex.: acessório ainda não)."""
    if chave[0] == "mat":
        pos, nome = CUBO_TIPO_MATERIAL, "Material"
    elif chave[1] == 5:
        pos, nome = CUBO_TIPO_ACESSORIO, "Accessories"
    else:
        pos, nome = CUBO_TIPO_EQUIPAMENTO, "Equipment"
    if pos is None:
        print(f"  tipo '{nome}' ainda não calibrado — abortando.", flush=True)
        return False
    # lista mostra 'Material' quando aberta (opção sempre presente)
    _setar_dropdown(CUBO_TIPO_DROPDOWN, pos, (1177, 659, 1307, 712), "material")
    return True


def tier_para_nivel(nivel):
    """Tier de MAIOR limite_inferior <= nivel (item na borda de baixo).
    Devolve (limite_inferior, (x,y)) ou None se nenhum serve."""
    escolhido = None
    for lower, pos in NIVEL_TIERS:
        if lower <= nivel:
            escolhido = (lower, pos)
    return escolhido


def selecionar_nivel(nivel):
    """Abre o dropdown de faixa e escolhe o tier do nível. False se não há tier."""
    tier = tier_para_nivel(nivel)
    if tier is None:
        return False
    # lista de faixas mostra '~' quando aberta (ex.: 'Lv 1~10')
    _setar_dropdown(CUBO_NIVEL_DROPDOWN, tier[1], (1337, 428, 1415, 500), "~")
    return True


def chave_sintese(it):
    """Chave de agrupamento p/ síntese, ou None se o item não sintetiza. É
    CANÔNICA (independe de onde o item está agora): o stash do equipamento vem do
    TIPO (stash_do_equip), não de it['stash'] — assim um item no Stash 7 casa com
    o grupo do setor de destino.
      - Material: ('mat', categoria, grade)        -> 9 mesmo grade+categoria
      - Equipamento: ('eq', stash_destino, grade, nivel) -> 9 mesmo grade+nível"""
    grade = it.get("grade")
    if not grade:
        return None
    mat = ith.material_info(it["nome"])
    if mat:
        categoria = mat[1]
        if categoria not in CATEGORIAS_SINTETIZAVEIS:   # soulstone/inscription/offering não fundem
            return None
        return ("mat", categoria, grade)
    st = ith.stash_do_equip(it["nome"])
    if it.get("nivel") is not None and st is not None:
        return ("eq", st, grade, it["nivel"])
    return None


def _grade_da_chave(k):
    return k[2]   # ('mat',cat,grade) e ('eq',stash,grade,nivel): grade no índice 2


def _descr_chave(k):
    if k[0] == "mat":
        return f"{k[2]} {k[1]}"
    return f"{k[2]} Lv.{k[3]} (stash {k[1]})"


def _cubo_slot_ocupado(idx):
    """True se o slot 'idx' (0..8) do cubo está ocupado. Para o mouse antes."""
    r, c = idx // CUBO_COLUNAS, idx % CUBO_COLUNAS
    inv.deslizar_mouse(*inv.ponto_descanso())
    time.sleep(inv.ATRASO_HOVER)
    return not inv.slot_vazio(inv.capturar_tela(), r, c, CUBO_X, CUBO_Y)


def _colocar_no_cubo(origem, idx):
    """Pega em 'origem' e solta no slot 'idx' do cubo, VERIFICANDO que ficou
    ocupado (re-solta se o clique cair). True se colocou."""
    destino = inv.slot_centro(idx // CUBO_COLUNAS, idx % CUBO_COLUNAS,
                              CUBO_X, CUBO_Y)
    for _ in range(2):
        pegar_e_soltar(origem, destino)
        if _cubo_slot_ocupado(idx):
            return True
        clicar(*destino)                 # place pode ter caído (item no cursor)
        time.sleep(PAUSA_PEGA_SOLTA)
        if _cubo_slot_ocupado(idx):
            return True
    return False


def _origem_no_jogo(it):
    """Centro do slot de origem do item, conforme a fonte:
       'bau' -> grade do baú; senão -> grade do STASH (aba já ativa)."""
    if it["stash"] == "bau":
        return inv.slot_centro(it["r"], it["c"], inv.BAU_X, inv.BAU_Y)
    return inv.slot_centro(it["r"], it["c"])


def _encher_cubo_e_fundir(chave, itens, verificar=True):
    """Enche o cubo com os 9 'itens' e funde. Cada item tem 'stash' = nº da aba
    (pega da grade do STASH, trocando de aba) OU 'bau' (pega DIRETO da grade do
    baú — o cubo aceita itens do baú). O cubo MANTÉM os já colocados ao trocar de
    aba, então dá p/ misturar setor + Stash 7 + baú. Cada colocação é verificada.
    Itens devem vir agrupados por fonte e reverse por posição (reflow-safe).
    'verificar' = confere por hover (do modelo); desliga quando os dados já são
    de leitura fresca (posições certas)."""
    # rede de segurança: confere por hover que os itens do modelo batem ANTES de
    # mexer no cubo (se o modelo divergir, invalida e re-lê — sem item errado).
    if verificar and not _verificar_synth(itens, chave):
        return False
    selecionar_modo_synthesis()
    if not selecionar_tipo(chave):
        return False
    if chave[0] == "eq":
        if not selecionar_nivel(chave[3]):
            print(f"  sem faixa de nível p/ Lv.{chave[3]} — abortando.", flush=True)
            return False
        print(f"  faixa: tier {tier_para_nivel(chave[3])[0]}~ (Lv.{chave[3]})",
              flush=True)
    afetadas = {it["stash"] for it in itens if it["stash"] != "bau"}
    aba = None
    for i, it in enumerate(itens):
        if it["stash"] != "bau" and it["stash"] != aba:
            if not garantir_aba(it["stash"]):
                modelo_invalidar()
                return False
            aba = it["stash"]
        if not _colocar_no_cubo(_origem_no_jogo(it), i):
            print(f"  falha ao colocar item {i + 1}/9 no cubo — abortando síntese.",
                  flush=True)
            for s in afetadas:
                modelo_invalidar(s)
            return False
    clicar(*BOTAO_SYNTH)
    time.sleep(PAUSA_TROCA_ABA)
    if CONFIRM_SYNTH:
        clicar(*CONFIRM_SYNTH)
        time.sleep(PAUSA_TROCA_ABA)
    if not _esperar_sintese():
        print("  síntese não concluiu a tempo (slots não esvaziaram); abortando.",
              flush=True)
        for s in afetadas:
            modelo_invalidar(s)
        return False
    clicar(*inv.slot_centro(1, 1, CUBO_X, CUBO_Y))   # resultado -> baú
    time.sleep(PAUSA_PEGA_SOLTA)
    inv.mover_mouse(*inv.ponto_descanso())
    for s in afetadas:    # tira os consumidos do modelo e compacta (organiza)
        modelo_remove(s, [it for it in itens if it["stash"] == s])
        _compactar_modelo(s)
    print(f"  síntese feita: {SYNTH_QTD}x {_descr_chave(chave)} -> 1 (grade acima), "
          f"resultado no baú.", flush=True)
    return True


def _ordenar_reverse(itens):
    """Reverse por posição (reflow-safe ao tirar do stash)."""
    return sorted(itens, key=lambda it: (it["r"], it["c"]), reverse=True)


def _grupos_por_chave(stash_itens):
    grupos = {}
    for it in stash_itens:
        k = chave_sintese(it)
        if k:
            grupos.setdefault(k, []).append(it)
    return grupos


def _synth_item(it, r, c, fonte):
    """Item pronto p/ o cubo: 'stash' = fonte (nº da aba ou 'bau'), + pos."""
    return {"stash": fonte, "r": r, "c": c, "nome": it.get("nome"),
            "grade": it.get("grade"), "nivel": it.get("nivel")}


def _grupos_modelo(stash):
    """Agrupa os itens da stash (do MODELO em memória, SEM re-ler) por chave de
    síntese; cada item já com posição (r,c) e fonte=stash. -> {chave:[synth_item]}"""
    grupos = {}
    for it, r, c in modelo_com_pos(stash):
        k = chave_sintese(it)
        if k:
            grupos.setdefault(k, []).append(_synth_item(it, r, c, stash))
    return grupos


def _verificar_synth(itens, chave):
    """Confere por HOVER que os itens de stash/Stash7 (vindos do MODELO) estão na
    posição esperada e com a chave certa — antes de colocá-los no cubo. Se algum
    divergir (modelo desatualizado por ruído de OCR), INVALIDA o modelo daquela
    stash e devolve False (não coloca item errado no cubo). Itens 'bau' vêm de
    leitura fresca, não precisam conferir. ~8 hovers em vez de re-ler 49."""
    por_stash = {}
    for it in itens:
        if it["stash"] != "bau":
            por_stash.setdefault(it["stash"], []).append(it)
    for s, lst in por_stash.items():
        if not garantir_aba(s):
            modelo_invalidar(s)
            return False
        for it in lst:
            nome, linhas = inv.ler_item_por_hover(it["r"], it["c"])
            cx, _cy = inv.slot_centro(it["r"], it["c"])
            _d, grade, nivel = classificar_completo(nome, linhas, cx)
            if chave_sintese({"nome": nome, "grade": grade, "nivel": nivel}) != chave:
                print(f"    modelo divergiu em Stash {s} ({it['r']},{it['c']}): "
                      f"{nome!r} ({grade}) — re-lendo a stash.", flush=True)
                modelo_invalidar(s)
                return False
    return True


def sintetizar(stash, dry=False):
    """Síntese SINGLE-stash: acha um grupo de SYNTH_QTD na própria 'stash'
    (grade mais BAIXO), funde e manda o resultado pro baú. True se sintetizou."""
    grupos = _grupos_modelo(stash)
    ordem = {g: i for i, g in enumerate(GRADES)}
    cand = sorted([(k, v) for k, v in grupos.items() if len(v) >= SYNTH_QTD],
                  key=lambda kv: ordem.get(_grade_da_chave(kv[0]), 99))
    if not cand:
        print(f"  Stash {stash}: nenhum grupo de {SYNTH_QTD} para sintetizar.",
              flush=True)
        return False
    chave, grupo = cand[0]
    escolhidos = _ordenar_reverse(grupo)[:SYNTH_QTD]
    print(f"  alvo da síntese: {_descr_chave(chave)} "
          f"({len(grupo)} disponíveis, usando {SYNTH_QTD})", flush=True)
    for it in escolhidos:
        print(f"    - ({it['r']},{it['c']}) {it['nome']!r}", flush=True)
    if dry:
        return True
    return _encher_cubo_e_fundir(chave, escolhidos)


def mover_bau_para_stash7(fodder):
    """Move os itens 'fodder' (do baú) p/ slots vazios do Stash 7 (ACUMULA p/ a
    fila de síntese). Devolve as novas posições [{stash:7,r,c}]. Pega do baú em
    reverse (reflow-safe) e usa o move verificado (robusto a clique perdido)."""
    staged = []
    for b in _ordenar_reverse(fodder):
        if not garantir_aba(STASH_STAGING):
            break
        vazio = modelo_proximo_vazio(STASH_STAGING)
        if vazio is None:
            print("  Stash 7 cheio — não dá p/ estagiar mais.", flush=True)
            break
        origem = inv.slot_centro(b["r"], b["c"], inv.BAU_X, inv.BAU_Y)
        if not _mover_verificado(origem, inv.slot_centro(*vazio), vazio):
            print("  falha ao estagiar item no Stash 7.", flush=True)
            modelo_invalidar(STASH_STAGING)
            break
        modelo_add(STASH_STAGING, b)
        staged.append(_synth_item(b, vazio[0], vazio[1], STASH_STAGING))
    return staged


def _grupos_frescos(stash):
    """Como _grupos_modelo, mas LENDO a stash do jogo (posições reais). Usado no
    fallback quando o modelo diverge (item misplaced/OCR ruidoso)."""
    grupos = {}
    for it in ler_stash_aba(stash):
        k = chave_sintese(it)
        if k:
            grupos.setdefault(k, []).append(_synth_item(it, it["r"], it["c"], stash))
    return grupos


def stash_do_item(nome):
    """Stash CORRETA do item pelo nome (onde ele deveria estar), ou None se
    desconhecido (OCR ruidoso -> não mexe, por segurança)."""
    mat = ith.material_info(nome)
    if mat:
        return mat[2]
    st = ith.stash_do_equip(nome)
    if st is not None:
        return st
    if "ulstone" in re.sub(r"[^a-z]", "", (nome or "").lower()):
        return 6
    return None


def _bau_slots_vazios():
    """[(r,c)] dos slots VAZIOS do baú (mouse fora)."""
    inv.deslizar_mouse(*inv.ponto_descanso())
    time.sleep(inv.ATRASO_HOVER)
    tela = inv.capturar_tela()
    return [(r, c) for r in range(inv.BAU_LINHAS) for c in range(inv.BAU_COLUNAS)
            if inv.slot_vazio(tela, r, c, inv.BAU_X, inv.BAU_Y)]


def _mover_stash_para_bau(origem, destino, bslot):
    """Pega na stash e solta no baú, verificando que o slot do baú ficou ocupado."""
    for _ in range(2):
        pegar_e_soltar(origem, destino)
        inv.deslizar_mouse(*inv.ponto_descanso())
        time.sleep(inv.ATRASO_HOVER)
        if not inv.slot_vazio(inv.capturar_tela(), bslot[0], bslot[1],
                              inv.BAU_X, inv.BAU_Y):
            return True
        clicar(*destino)
        time.sleep(PAUSA_PEGA_SOLTA)
    return False


def tirar_fora_do_lugar(stash):
    """Move pro BAÚ os itens que NÃO pertencem a esta stash (classificação !=
    stash; itens de nome desconhecido NÃO são tocados). Libera espaço e conserta
    o lugar errado — depois o baú reclassifica. Devolve True se moveu algum."""
    fora = [(it, r, c) for it, r, c in modelo_com_pos(stash)
            if (d := stash_do_item(it.get("nome"))) is not None and d != stash]
    if not fora:
        return False
    vazios = _bau_slots_vazios()
    if not vazios:
        print("  baú sem slot visível p/ tirar item fora-do-lugar — fica p/ depois.",
              flush=True)
        return False
    if not garantir_aba(stash):
        return False
    moveu = False
    for it, r, c in sorted(fora, key=lambda x: (x[1], x[2]), reverse=True):
        if not vazios:
            break
        # CONFERE por hover que o slot tem MESMO um item fora-do-lugar (caso o
        # modelo tenha divergido aqui) — só move se confirmado.
        nome, linhas = inv.ler_item_por_hover(r, c)
        dest = stash_do_item(nome)
        if dest is None or dest == stash:
            modelo_invalidar(stash)
            continue
        bslot = vazios.pop()
        origem = inv.slot_centro(r, c)
        destino = inv.slot_centro(bslot[0], bslot[1], inv.BAU_X, inv.BAU_Y)
        if _mover_stash_para_bau(origem, destino, bslot):
            modelo_remove(stash, [it])
            print(f"  fora-do-lugar: {nome!r} (Stash {stash} -> baú, "
                  f"vai p/ Stash {dest})", flush=True)
            moveu = True
        else:
            modelo_invalidar(stash)
            break
    if moveu:
        _compactar_modelo(stash)
    return moveu


def liberar_espaco(stash, bau_itens=None):
    """Resolve uma stash CHEIA. ANTES de sintetizar, tira itens fora-do-lugar pro
    baú (libera espaço e conserta). Depois tenta com o MODELO (rápido); se divergir
    (a síntese falha na verificação), re-tenta com LEITURA FRESCA da stash
    (posições reais). 'bau_itens' = baú já lido pelo chamador (evita re-ler+re-sort
    o baú); se None, lê fresco. Devolve 'synth' | 'staged' | 'nada'."""
    if tirar_fora_do_lugar(stash):
        return "staged"   # liberou espaço movendo item fora-do-lugar -> re-lê baú
    r = _liberar(stash, False, bau_itens)
    if r == "_retry":
        print("  -> tentando de novo com leitura fresca da stash.", flush=True)
        r = _liberar(stash, True, bau_itens)
    return "nada" if r == "_retry" else r


def _liberar(stash, fresco, bau_itens=None):
    """Lógica de liberar_espaco. 'fresco' = ler stash/Stash7 do jogo (posições
    certas, sem verificação) em vez do modelo. 'bau_itens' = baú já lido (evita
    re-ler). Devolve 'synth'|'staged'|'nada' ou '_retry' (modelo divergiu ->
    o wrapper tenta fresco)."""
    grupos = _grupos_frescos(stash) if fresco else _grupos_modelo(stash)
    ordem = {g: i for i, g in enumerate(GRADES)}
    verif = not fresco   # dados frescos não precisam reverificar por hover

    comp = sorted([(k, v) for k, v in grupos.items() if len(v) >= SYNTH_QTD],
                  key=lambda kv: ordem.get(_grade_da_chave(kv[0]), 99))
    if comp:
        k, v = comp[0]
        print(f"  síntese SINGLE na Stash {stash}: {_descr_chave(k)}", flush=True)
        if _encher_cubo_e_fundir(k, _ordenar_reverse(v)[:SYNTH_QTD], verificar=verif):
            return "synth"
        return "_retry" if not fresco else "nada"

    grupos7 = _grupos_frescos(STASH_STAGING) if fresco else _grupos_modelo(STASH_STAGING)
    # SÓ considera fodder que PERTENCE a esta stash: itens do baú/Stash7 destinados
    # a OUTRAS stashes não ajudam a liberar 'stash' e não podem ser sintetizados/
    # estagiados aqui (ex.: Decoration tem casa na Stash 3, não vira fila no 7).
    grupos7 = {k: v for k, v in grupos7.items()
               if v and stash_do_item(v[0].get("nome")) == stash}
    # reaproveita o baú já lido pelo chamador (sem re-ler/re-sortear); só lê se
    # ninguém passou. O baú não recompacta dentro da passada, então as posições
    # (r,c) dos itens não-movidos continuam válidas.
    itens_bau = bau_itens if bau_itens is not None else ler_bau(salvar_debug=False)
    bau_por_chave = {}
    for b in itens_bau:
        if stash_do_item(b.get("nome")) != stash:
            continue
        k = chave_sintese(b)
        if k:
            bau_por_chave.setdefault(k, []).append(b)

    def total(k):
        return (len(grupos.get(k, [])) + len(grupos7.get(k, []))
                + len(bau_por_chave.get(k, [])))

    # Considera TODAS as chaves (stash + Stash7 + baú), não só as da stash. Assim
    # uma enxurrada no baú (ex.: 11x common Lv.65 p/ uma stash cheia) pode ser
    # sintetizada 100% do baú, consolidando o fluxo em vez de travar. Prioriza
    # quem CONTRIBUI da stash (libera espaço de fato) e depois o maior grupo.
    todas = set(grupos) | set(grupos7) | set(bau_por_chave)
    cands = sorted(todas,
                   key=lambda k: (0 if grupos.get(k) else 1,
                                  -total(k), ordem.get(_grade_da_chave(k), 99)))

    # CROSS/BAÚ DIRETO: stash + Stash7(acumulado) + baú fecham 9 (vão DIRETO p/ cubo)
    for k in cands:
        if total(k) < SYNTH_QTD:
            continue
        gstash = _ordenar_reverse(grupos.get(k, []))
        n = len(gstash)
        falta = SYNTH_QTD - n
        s7_itens = _ordenar_reverse(grupos7.get(k, []))[:falta]
        bau_itens = _ordenar_reverse(bau_por_chave.get(k, []))[:falta - len(s7_itens)]
        bau_marc = [_synth_item(x, x["r"], x["c"], "bau") for x in bau_itens]
        itens9 = gstash + s7_itens + bau_marc
        origem = "CROSS" if n or s7_itens else "BAÚ"
        print(f"  síntese {origem} na Stash {stash}: {_descr_chave(k)} "
              f"({n} setor + {len(s7_itens)} Stash7 + {len(bau_marc)} baú)",
              flush=True)
        if _encher_cubo_e_fundir(k, itens9[:SYNTH_QTD], verificar=verif):
            return "synth"
        return "_retry" if not fresco else "nada"

    # ninguém fecha 9: ACUMULA no Stash 7 o fodder do melhor grupo (fila)
    for k in cands:
        fodder = bau_por_chave.get(k)
        if fodder:
            print(f"  acumulando {len(fodder)}x {_descr_chave(k)} no Stash 7 "
                  f"(fila de síntese).", flush=True)
            return "staged" if mover_bau_para_stash7(fodder) else "nada"
    return "nada"


# --- Modos -----------------------------------------------------------------
def modo_ler():
    print("DRY-RUN: lendo o baú e classificando (NÃO move nada).")
    print("Abra o jogo com o inventário/baú visível. NÃO mexa no mouse.\n")
    itens = ler_bau(salvar_debug=True)
    print(f"\n{len(itens)} itens no baú.")
    naorec = [i for i in itens if i["stash"] is None]
    if naorec:
        print(f"⚠ {len(naorec)} não reconhecidos: "
              f"{[i['nome'] for i in naorec]}")
    print("-> Debug das leituras em 'debug_hover/bau_L_C.png'.")


def modo_abas():
    print("Testando as 7 abas: clica em cada uma e DETECTA qual ficou ativa.")
    print("NÃO mexa no mouse. Confira no jogo se a aba que acende é a mesma.\n")
    for s in range(1, 8):
        _clicar_aba(s)
        inv.deslizar_mouse(*inv.ponto_descanso())
        time.sleep(inv.ATRASO_HOVER)
        ativa = aba_ativa(inv.capturar_tela())
        marca = "OK" if ativa == s else "‼ DIVERGE"
        print(f"  cliquei aba {s}  ->  detectada ativa = {ativa}   {marca}",
              flush=True)
        time.sleep(0.3)
    inv.mover_mouse(*inv.ponto_descanso())


def modo_lerdbg(r, c):
    """Lê UM slot do baú e imprime TODAS as linhas do OCR (com X e centro) e o
    nome escolhido — para depurar a seleção do nome quando há 2 tooltips."""
    print(f"Lendo baú ({r},{c}) — mostra todas as linhas do OCR. NÃO mexa no mouse.")
    print("Começando em 5s...\n")
    for s in range(5, 0, -1):
        print(f"  {s}...", end="\r", flush=True)
        time.sleep(1)
    print("Iniciado!        \n")
    nome, linhas = inv.ler_item_por_hover(
        r, c, gx=inv.BAU_X, gy=inv.BAU_Y, ref_y=BAU_REF_Y,
        faixa_x=BAU_NOME_X, salvar_debug=True, prefixo_debug="lerdbg")
    cx, _cy = inv.slot_centro(r, c, inv.BAU_X, inv.BAU_Y)
    print(f"cx do slot = {cx}\n")
    print("linhas do OCR (y, x1-x2, centroX, texto):")
    for topo, x1, x2, txt in linhas:
        print(f"  y={topo:4d}  x={int(x1):4d}-{int(x2):4d}  "
              f"cx={int((x1 + x2) / 2):4d}  {txt!r}", flush=True)
    print(f"\n=> nome escolhido: {nome!r}")
    inv.mover_mouse(*inv.ponto_descanso())


def modo_sintetizar(stash, dry=False):
    """Testa a síntese numa stash: acha um grupo de 9 e (se não for dry) funde."""
    acao = "PLANO (dry, não mexe)" if dry else "VAI SINTETIZAR de verdade"
    print(f"Síntese na Stash {stash} — {acao}.")
    print("Cubo precisa estar VAZIO. NÃO mexa no mouse. Começando em 5s...\n")
    for s in range(5, 0, -1):
        print(f"  {s}...", end="\r", flush=True)
        time.sleep(1)
    print("Iniciado!        \n")
    try:
        sintetizar(stash, dry=dry)
    except KeyboardInterrupt:
        print("\nInterrompido.")
    finally:
        inv.mover_mouse(*inv.ponto_descanso())


def modo_liberar(stash):
    """Testa liberar_espaco(stash): lê o baú e tenta sintetizar (single OU cross
    com fodder do baú via Stash 7). VAI mexer no jogo."""
    print(f"Teste de liberar_espaco na Stash {stash} (single ou cross). VAI mexer!")
    print("Cubo VAZIO. NÃO mexa no mouse. Começando em 5s...\n")
    for s in range(5, 0, -1):
        print(f"  {s}...", end="\r", flush=True)
        time.sleep(1)
    print("Iniciado!        \n")
    try:
        res = liberar_espaco(stash)
        print(f"\n=> resultado: {res} "
              f"({'sintetizou' if res=='synth' else 'acumulou no Stash 7' if res=='staged' else 'nada a fazer'})")
    except KeyboardInterrupt:
        print("\nInterrompido.")
    finally:
        inv.mover_mouse(*inv.ponto_descanso())


def modo_vagas(stash=None):
    """Diagnóstico: vai para a aba 'stash' (se dada) e imprime brilho/saturação
    e o veredito de slot_vazio de cada slot do STASH. Serve para calibrar a
    detecção de vaga (ex.: na Stash 1, que fica quase cheia)."""
    print("Diagnóstico de slots vazios do STASH. NÃO mexa no mouse.")
    print("Começando em 5s...\n")
    for s in range(5, 0, -1):
        print(f"  {s}...", end="\r", flush=True)
        time.sleep(1)
    print("Iniciado!        \n")

    if stash:
        if not trocar_aba(stash):
            print(f"Não consegui ativar a aba {stash}.")
            inv.mover_mouse(*inv.ponto_descanso())
            return
        print(f"Aba ativa: Stash {stash}\n")

    inv.deslizar_mouse(*inv.ponto_descanso())
    time.sleep(inv.ATRASO_HOVER)
    tela = inv.capturar_tela()
    vazias = []
    for r in range(inv.LINHAS):
        celulas = []
        for c in range(inv.COLUNAS):
            x1, y1, x2, y2 = inv.slot_bbox(r, c)
            crop = tela[y1 + 4:y2 - 4, x1 + 4:x2 - 4]
            b = float(inv.cv2.cvtColor(crop, inv.cv2.COLOR_BGR2GRAY).mean())
            sa = float(inv.cv2.cvtColor(crop, inv.cv2.COLOR_BGR2HSV)[:, :, 1].mean())
            vazio = inv.slot_vazio(tela, r, c)
            if vazio:
                vazias.append((r, c))
            tag = "VAZIO" if vazio else "ocup "
            celulas.append(f"b{b:4.0f} s{sa:4.0f} {tag}")
        print(f"  L{r}: " + " | ".join(celulas), flush=True)
    print(f"\nVagas detectadas: {vazias if vazias else 'NENHUMA'}")
    inv.mover_mouse(*inv.ponto_descanso())


def modo_mover(limite=None):
    """Esvazia o baú: para cada item, vai para a aba do seu tipo, acha um slot
    vazio e move (pega/solta). Organiza o STASH a cada 5 e dá sort no baú a
    cada 10. 'limite' = parar após N movimentos (para testes)."""
    print("MODO MOVER — vai mexer no jogo de verdade!")
    print(f"Limite de movimentos: {limite if limite else 'sem limite'}")
    parada.instalar()   # atalho global Alt+ç (idempotente)
    print("Foque o jogo. Para abortar: Alt+ç (ou Ctrl+C). Começando em 5s...\n")
    for s in range(5, 0, -1):
        print(f"  {s}...", end="\r", flush=True)
        time.sleep(1)
    print("Iniciado!        \n")

    # O modelo em memória só vale DENTRO de uma execução. Entre ciclos do loop
    # (ou se o jogo/usuário mexeu nas stashes), ele fica velho. Descarta tudo e
    # RE-LÊ todas as 7 stashes agora (incl. a 7/staging), p/ o modelo casar com
    # a realidade desde o início e evitar erros (ex.: achar que uma stash mexida
    # está cheia e disparar síntese à toa).
    modelo_invalidar()
    print("  re-lendo as 7 stashes...", flush=True)
    for s in range(1, 8):
        n = len(modelo_stash(s))
        print(f"    Stash {s}: {n} itens", flush=True)

    movidos = 0
    pulados = []   # (nome, motivo)
    try:
        for passada in range(LIMITE_PASSADAS):
            itens = ler_bau(salvar_debug=False)
            if not itens:
                print("\nBaú vazio. Concluído.")
                break

            movidos_passada = 0
            sintetizou = False
            synth_tentado = set()   # stashes já tentadas nesta passada (evita loop)
            # AGRUPA por aba de destino (menos trocas de aba): a cada passo prefere
            # um item cuja stash já é a aba ATIVA. Modela o baú como lista com o
            # índice de slot (si) de cada item; ao MOVER um, os de trás escorregam
            # (si-1) — reflow-safe independente da ordem de escolha.
            bc = inv.BAU_COLUNAS
            bau = [{"it": it, "si": it["r"] * bc + it["c"], "skip": False}
                   for it in itens]
            while True:
                cands = [e for e in bau if not e["skip"]]
                if not cands:
                    break
                pref = [e for e in cands if e["it"]["stash"] == _aba_atual]
                e = (pref or cands)[0]
                it = e["it"]
                nome, stash, si = it["nome"], it["stash"], e["si"]

                if stash is None:
                    e["skip"] = True
                    pulados.append((nome, "tipo não reconhecido"))
                    print(f"  PULA {nome!r}: tipo não reconhecido", flush=True)
                    continue
                if not garantir_aba(stash):
                    e["skip"] = True
                    pulados.append((nome, f"não consegui ativar a aba {stash}"))
                    print(f"  PULA {nome!r}: aba {stash} não ativou", flush=True)
                    continue

                vazio = modelo_proximo_vazio(stash)   # do MODELO (sem re-ler)
                if vazio is None:
                    # PRIORIDADE 1: síntese (uma vez por stash por passada).
                    if stash in synth_tentado:
                        e["skip"] = True
                        continue
                    synth_tentado.add(stash)
                    print(f"  Stash {stash} cheia -> liberar/acumular...", flush=True)
                    # passa o baú JÁ lido (itens não-movidos, posições válidas) p/
                    # não re-ler+re-sortear o baú dentro do liberar.
                    bau_atual = [x["it"] for x in bau if not x["skip"]]
                    res = liberar_espaco(stash, bau_atual)
                    if res in ("synth", "staged"):
                        sintetizou = True
                        print(f"  progresso ({res}) — relendo o baú.", flush=True)
                        break   # posições do baú mudaram -> re-lê
                    e["skip"] = True
                    pulados.append((nome, f"Stash {stash} cheia (sem síntese/staging)"))
                    print(f"  PULA {nome!r}: Stash {stash} cheia, nada agora "
                          f"(fila — segue organizando os outros)", flush=True)
                    continue

                origem = inv.slot_centro(si // bc, si % bc, inv.BAU_X, inv.BAU_Y)
                destino = inv.slot_centro(*vazio)
                if not _mover_verificado(origem, destino, vazio):
                    modelo_invalidar(stash)   # modelo pode ter divergido -> re-lê
                    pulados.append((nome, f"falhou ao mover p/ {vazio} (clique perdido)"))
                    print(f"  FALHOU {nome!r}: não colocou em {vazio} após 2 "
                          f"tentativas — ABORTANDO (confira o jogo).", flush=True)
                    return _resumo(movidos, pulados)

                movidos += 1
                movidos_passada += 1
                modelo_add(stash, it)         # registra no modelo (slot no fim)
                print(f"  [{movidos}] {nome!r} -> Stash {stash} slot {vazio}",
                      flush=True)
                # MOVEU: marca como feito. O baú NÃO recompacta dentro da passada
                # (deixa o buraco até o sort), então os outros mantêm o slot original.
                e["skip"] = True

                if limite and movidos >= limite:
                    print("\nLimite atingido. Parando.")
                    return _resumo(movidos, pulados)
                if movidos_passada >= SORTEAR_BAU_A_CADA:
                    break  # já moveu 10 desta vista -> sai p/ sortear e re-ler

            # (o sort do baú agora é feito no início de ler_bau, na re-leitura)

            # parar só se NÃO houve progresso (nem move nem síntese) — assim a
            # "fila" de stashes cheias é re-tentada enquanto algo evolui.
            if movidos_passada == 0 and not sintetizou:
                print("\nNenhum progresso nesta passada (nem move nem síntese) — "
                      "parando.")
                break
        else:
            print("\nLimite de passadas atingido (segurança).")
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário.")
    finally:
        inv.mover_mouse(*inv.ponto_descanso())
    return _resumo(movidos, pulados)


def _toplevel(win):
    """Sobe da janela até o nível-topo (filho direto da raiz)."""
    rid = inv._root.id
    w = win
    for _ in range(12):
        try:
            p = w.query_tree().parent
        except Exception:
            return w
        if p is None or p.id == rid:
            return w
        w = p
    return w


def jogo_ativo():
    """True se a janela do jogo é a ATIVA (em foco/na frente) — assim os cliques
    XTEST vão pro jogo. Usa _NET_ACTIVE_WINDOW. (map_state não serve: este
    compositor mantém a janela 'IsViewable' mesmo minimizada.)"""
    try:
        win, *_ = inv.localizar_janela(forcar=True)
        na = inv._display.intern_atom('_NET_ACTIVE_WINDOW')
        prop = inv._root.get_full_property(na, inv.X.AnyPropertyType)
        if not prop or not prop.value:
            return False
        return prop.value[0] in (win.id, _toplevel(win).id)
    except Exception:
        return False


def garantir_jogo(tentativas=4):
    """Garante o jogo em foco/na frente. Se não estiver, clica no ícone da barra
    de tarefas (ICONE_BARRA) p/ trazê-lo (e não toggla, pois só clica se NÃO
    estiver ativo). True se ficou ativo."""
    for _ in range(tentativas):
        if jogo_ativo():
            return True
        print(f"  jogo não está em foco — clicando no ícone da barra {ICONE_BARRA}...",
              flush=True)
        clicar(*ICONE_BARRA)
        time.sleep(2.0)
    return jogo_ativo()


def relatorio_valor_top(n=5):
    """Imprime os N itens de MAIOR valor de mercado (Steam, BRL) no inventário —
    usando o menor preço de venda pedido pelos membros (lowest sell price).
    Agrupa itens iguais (nome+grade+nível) e mostra a quantidade que você tem."""
    try:
        mercado.atualizar(verbose=True)   # garante cache (re-raspa se velho)
    except Exception as e:
        print(f"  (mercado indisponível: {e!r})", flush=True)
        return
    agg = {}   # (nome,grade,nivel) -> [centavos, qtd, set(stashes)]
    for s in range(1, 8):
        for it in modelo_stash(s):
            v = mercado.valor_cents(it.get("nome"), it.get("grade"), it.get("nivel"))
            if not v:
                continue
            k = (it.get("nome"), it.get("grade"), it.get("nivel"))
            reg = agg.setdefault(k, [v, 0, set()])
            reg[1] += 1
            reg[2].add(s)
    print(f"\n  === TOP {n} por valor de mercado (Steam, BRL) ===", flush=True)
    if not agg:
        print("    (nenhum item do inventário com listagem no mercado)", flush=True)
        return
    ranked = sorted(agg.items(), key=lambda kv: -kv[1][0])[:n]
    for (nome, grade, nivel), (cents, qtd, stashes) in ranked:
        lv = f" Lv.{nivel}" if nivel else ""
        st = "/".join(str(s) for s in sorted(stashes))
        print(f"    {mercado.fmt(cents):>11}  {nome} [{grade or '?'}{lv}]"
              f"  x{qtd}  (Stash {st})", flush=True)


def modo_loop(intervalo_min=INTERVALO_LOOP_MIN):
    """Organiza o inventário, espera 'intervalo_min' min e repete. Antes de cada
    ciclo, garante o jogo aberto (clica a barra de tarefas se preciso). Ctrl+C
    durante a espera para o loop."""
    print(f"MODO LOOP — organiza e repete a cada {intervalo_min} min.")
    parada.instalar()   # atalho global Alt+ç (para de qualquer janela)
    print("Pare a qualquer momento com Alt+ç (ou Ctrl+C no terminal).\n")
    ciclo = 0
    try:
        while True:
            ciclo += 1
            print(f"\n========== Ciclo {ciclo} ==========", flush=True)
            if garantir_jogo():
                modo_mover()
                if parada.parar.is_set():    # Alt+ç durante o mover: não rasta o mercado
                    break
                relatorio_valor_top()
            else:
                print("  não consegui abrir o jogo — pulando este ciclo.", flush=True)
            if parada.parar.is_set():
                break
            print(f"\nAguardando {intervalo_min} min até o próximo ciclo "
                  f"(Alt+ç ou Ctrl+C para parar)...", flush=True)
            for m in range(1, intervalo_min + 1):
                for _ in range(60):          # dorme 1s por vez p/ reagir ao Alt+ç
                    if parada.parar.is_set():
                        raise KeyboardInterrupt
                    time.sleep(1)
                print(f"  {m}/{intervalo_min} min "
                      f"(faltam {intervalo_min - m})", flush=True)
    except KeyboardInterrupt:
        print("\nLoop interrompido"
              f"{' (Alt+ç)' if parada.parar.is_set() else ' pelo usuário'}.")
    finally:
        inv.mover_mouse(*inv.ponto_descanso())


def _resumo(movidos, pulados):
    print(f"\n=== Resumo: {movidos} itens movidos ===")
    if pulados:
        print(f"{len(pulados)} pulados:")
        for nome, motivo in pulados:
            print(f"   {nome!r}: {motivo}")


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "ler"
    if modo == "ler":
        modo_ler()
    elif modo == "abas":
        modo_abas()
    elif modo == "vagas":
        stash = int(sys.argv[2]) if len(sys.argv) > 2 else None
        modo_vagas(stash)
    elif modo == "lerdbg":
        modo_lerdbg(int(sys.argv[2]), int(sys.argv[3]))
    elif modo == "escanear":
        escanear_stashs(salvar_debug=False)
    elif modo == "sintetizar":
        stash = int(sys.argv[2])
        dry = len(sys.argv) > 3 and sys.argv[3] == "dry"
        modo_sintetizar(stash, dry=dry)
    elif modo == "liberar":
        modo_liberar(int(sys.argv[2]))
    elif modo == "mover":
        # 'mover N' = para após N movimentos (recomendado p/ o 1º teste, ex.: 1)
        limite = int(sys.argv[2]) if len(sys.argv) > 2 else None
        modo_mover(limite)
    elif modo == "valor":
        # 'valor [N]' = lê as 7 stashes e mostra os N itens de maior valor de mercado
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        modelo_invalidar()
        for s in range(1, 8):
            modelo_stash(s)
        relatorio_valor_top(n)
    elif modo == "loop":
        # 'loop [min]' = organiza e repete a cada [min] minutos (padrão 30)
        intervalo = int(sys.argv[2]) if len(sys.argv) > 2 else INTERVALO_LOOP_MIN
        modo_loop(intervalo)
    else:
        print(__doc__)
