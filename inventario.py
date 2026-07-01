"""
Organização automática de inventário do TaskbarHero — ETAPA 1: calibração + detecção.

Esta etapa NÃO move nada ainda. Ela serve para acertar a grade de slots e
conferir se o OCR consegue ler o tipo de cada equipamento. Depois que isso
estiver correto, a próxima etapa adiciona a lógica de agrupar/mover.

Captura SÓ a janela do jogo (achada pelo nome via Xlib — ignora IDE, terminal e
o resto da tela). O nome do item só aparece ao passar o mouse (hover), num painel
que abre à direita do slot. O OCR (RapidOCR, sem tesseract) olha só uma janela X
relativa ao slot (isola o item da mochila e exclui o item equipado, que o jogo
mostra mais à direita), descarta a linha de raridade ('... Grade') e pega a linha
de CIMA que sobra (o nome). Slot vazio = a janela não muda no hover.

Modos (veja o final do arquivo):
  - grade : desenha a grade p/ calibrar coords (salva 'debug_grade.png').
  - hover L C : testa o hover em UM slot e salva debug em 'debug_hover/'.
  - tudo  : lê o nome de TODOS os slots e imprime o mapa (linha, coluna).

Como usar:
  1. Abra o inventário no jogo.
  2. Ajuste a CONFIGURAÇÃO DA GRADE abaixo (coordenadas/tamanho dos slots).
     Dica: use 'python main.py pos' para descobrir coordenadas com o mouse.
  3. Rode:  python inventario.py
  4. Abra 'debug_grade.png' e veja se os retângulos batem com os slots.
     Se não baterem, ajuste GRADE_X/Y, SLOT_W/H, PASSO_X/Y e rode de novo.
"""

import ctypes
import glob
import os
import sys
import time

import cv2
import mss
import numpy as np


def _preload_cuda():
    """Pré-carrega as libs CUDA/cuDNN dos pacotes pip nvidia-* (instaladas no
    venv) ANTES de importar o onnxruntime — senão ele não acha 'libcudart.so.13'.
    Usa ctypes RTLD_GLOBAL; 2 passadas resolvem a ordem de dependência. Sem as
    libs (outra máquina), não faz nada e o OCR cai pra CPU."""
    libs = []
    for p in sys.path:
        for d in glob.glob(os.path.join(p, "nvidia", "*", "lib")):
            libs += glob.glob(os.path.join(d, "*.so*"))
    for _ in range(2):
        for lib in libs:
            try:
                ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass
    return bool(libs)


_TEM_CUDA = _preload_cuda()

from rapidocr_onnxruntime import RapidOCR  # noqa: E402 (depois do preload CUDA)
from Xlib import X, display  # noqa: E402
from Xlib.ext import xtest  # noqa: E402

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO DA GRADE — ajuste para o inventário do TaskbarHero
# ---------------------------------------------------------------------------
GRADE_X = 508      # x do canto superior-esquerdo do PRIMEIRO slot (linha 0, col 0)
GRADE_Y = 445       # y do canto superior-esquerdo do primeiro slot
SLOT_W = 40         # largura de um slot, em pixels
SLOT_H = 40         # altura de um slot, em pixels
PASSO_X = 40        # distância (px) de um slot ao seguinte na horizontal (borda a borda + espaço)
PASSO_Y = 40        # distância (px) de um slot ao seguinte na vertical
COLUNAS = 7         # número de colunas de slots
LINHAS = 7          # número de linhas de slots

# Segunda grade: o inventário 2x7 logo abaixo do painel HERO, onde caem os
# itens dos baús abertos. É de onde o script PEGA os itens para mover.
BAU_X = 831         # x do canto sup-esq do primeiro slot da grade dos baús
BAU_Y = 561         # y do canto sup-esq
BAU_LINHAS = 2      # linhas da grade dos baús
BAU_COLUNAS = 7     # colunas da grade dos baús

# Região do slot onde fica o texto do tipo. (0,0,1,1) = o slot inteiro.
# Se o nome/letra fica só numa faixa (ex.: rodapé), restrinja aqui em frações
# do slot: (esq, topo, dir, base). Ex.: (0.0, 0.7, 1.0, 1.0) = faixa de baixo.
AREA_TEXTO = (0.0, 0.0, 1.0, 1.0)

ESCALA_OCR = 3      # amplia o recorte Nx antes do OCR (ajuda em textos pequenos)

# --- Detecção por HOVER (o nome do item só aparece ao passar o mouse) -------
# O nome aparece numa "tooltip" que surge em posição dinâmica. O script
# descobre sozinho onde ela está: compara a tela SEM hover (mouse no ponto de
# descanso) com a tela COM hover; a região que muda é a tooltip.
PONTO_DESCANSO = None     # se None, calculado à esquerda da janela (ver ponto_descanso())
ATRASO_HOVER = 0.1           # TETO da espera do tooltip (fallback p/ baseline e cap do loop)
# Espera ADAPTATIVA do tooltip: em vez de dormir um tempo fixo, captura em loop e
# para assim que a região do nome está PRESENTE (difere da base) e ESTÁVEL (2
# frames seguidos quase iguais). Adapta-se à latência real do jogo (50fps =
# 20ms/frame); nunca passa do teto ATRASO_HOVER. Não é gargalo de CPU/GPU.
ATRASO_MIN = 0.04            # espera mínima antes da 1ª checagem (~2 frames @50fps)
POLL_INTERVALO = 0.012       # intervalo entre capturas no loop (~1 frame)
TOOLTIP_PRESENCA = 3.0       # diff médio (vs base) na região p/ "tooltip apareceu"
TOOLTIP_ESTAVEL = 1.2        # diff médio entre 2 frames p/ "parou de animar"
DIFF_LIMIAR = 25             # limiar de diferença de pixel (0-255) para detectar mudança
TOOLTIP_AREA_MIN = 400       # ignora mudanças menores que isso (px²) — ex.: o cursor
IGNORAR_RAIO_CURSOR = 24     # zera um quadrado deste raio ao redor do cursor no diff
# O jogo só dispara o hover com MOVIMENTO real (não basta o cursor surgir no
# lugar). Por isso movemos em vários passos e damos um "wiggle" no slot.
PASSOS_HOVER = 20            # nº de passos ao deslizar o mouse até o slot
WIGGLE_PX = 4               # amplitude (px) da mexidinha dentro do slot
PAUSA_PASSO = 0.001         # s entre cada passo do deslize

# --- Captura SÓ da janela do jogo (ignora IDE/terminal/resto da tela) -------
# A captura é feita direto da janela via Xlib (funciona mesmo com algo por cima,
# pois o compositor está ativo). Isso elimina o "ruído" do diff vindo do resto
# da tela (terminal imprimindo, relógio, etc.).
JANELA_NOME = "TaskBarHero"  # nome (ou parte) da janela do jogo

# --- Onde o NOME do item aparece -------------------------------------------
# O painel de info abre à DIREITA do slot. O NOME começa ~+75px do CENTRO do
# slot; o item EQUIPADO (comparação) fica bem mais longe (~+305px). Então:
#  - olhamos só uma janela X relativa ao centro do slot (NOME_DX) -> isola o
#    item da mochila e descarta o equipado;
#  - numa faixa Y logo abaixo do rótulo de classe do HERO (NOME_DY);
#  - descartamos linhas que contêm "Grade" (a linha de raridade);
#  - o NOME é a linha de CIMA que sobra (acima da descrição).
NOME_DX = (40, 215)    # janela X do nome, relativa ao CENTRO do slot (exclui equipado)
# Faixa Y ALTA: o nome sobe quando o tooltip é maior (mais stats). Cobrimos
# bastante altura; o que NÃO é o tooltip (ouro, painel HERO, classe) é estático
# e some no filtro por diff. Começa logo ABAIXO do ouro (~y251) p/ não pegá-lo.
NOME_DY = (-100, 210)  # faixa Y, relativa a GRADE_Y
NOME_ESCALA = 1        # NÃO ampliar (o OCR sai mais limpo no tamanho nativo)
# Linhas com estas palavras NÃO são o nome: "grade" (raridade) e os rótulos
# fixos do jogo "stash"/"hero" (podem vazar pelo diff na coluna do slot 0).
PALAVRAS_IGNORAR = ("grade", "stash", "hero")
# Só consideramos linhas que MUDARAM entre o "sem hover" e o "com hover" (=são
# do tooltip). Assim ignoramos ouro/HERO/classe (estáticos). Valor = média
# mínima do diff (0-255) na caixa da linha para contar como "do tooltip".
LINHA_DIFF_MIN = 12
# ---------------------------------------------------------------------------

PASTA = os.path.dirname(os.path.abspath(__file__))
PASTA_SLOTS = os.path.join(PASTA, "slots")
PASTA_DEBUG = os.path.join(PASTA, "debug_hover")

def _criar_ocr():
    """RapidOCR na GPU (CUDA) se as libs carregaram; senão CPU. O RapidOCR 1.2.x
    tem um bug: passar *_use_cuda exige passar *_model_path junto (None usa o
    padrão). Se a GPU falhar/cair, volta pra CPU.
    use_angle_cls=False: o texto do inventário é SEMPRE horizontal/upright; o
    classificador de ângulo às vezes gira texto curto 180° (ex.: Wood -> pooM)."""
    if _TEM_CUDA:
        try:
            return RapidOCR(use_angle_cls=False,
                            det_use_cuda=True, det_model_path=None,
                            rec_use_cuda=True, rec_model_path=None)
        except Exception as e:
            print(f"[OCR] CUDA indisponível ({e!r}); usando CPU.", flush=True)
    return RapidOCR(use_angle_cls=False)


_ocr = _criar_ocr()
_display = display.Display()
_root = _display.screen().root


def mover_mouse(x, y):
    """Move o ponteiro para (x, y) via XTEST (movimento absoluto, sem passos)."""
    xtest.fake_input(_display, X.MotionNotify, x=int(x), y=int(y))
    _display.sync()


def posicao_mouse():
    """Retorna (x, y) atual do ponteiro."""
    d = _root.query_pointer()._data
    return d["root_x"], d["root_y"]


def deslizar_mouse(x, y, passos=PASSOS_HOVER):
    """Move o ponteiro até (x, y) em vários passos, gerando eventos de
    MOVIMENTO reais (necessário para o jogo disparar o hover)."""
    x0, y0 = posicao_mouse()
    passos = max(1, passos)
    for i in range(1, passos + 1):
        t = i / passos
        mover_mouse(x0 + (x - x0) * t, y0 + (y - y0) * t)
        if PAUSA_PASSO:
            time.sleep(PAUSA_PASSO)
    mover_mouse(x, y)


def ponto_descanso():
    """Ponto (x, y) para 'estacionar' o mouse sem disparar tooltip: à esquerda
    da janela do jogo. Usa PONTO_DESCANSO se estiver definido."""
    if PONTO_DESCANSO is not None:
        return PONTO_DESCANSO
    _, ox, oy, _w, h = localizar_janela()
    return max(ox - 40, 5), oy + h // 2


def hover_no_slot(cx, cy):
    """Desliza até o slot e faz um pequeno wiggle para garantir que o jogo
    registre o cursor entrando no slot e mostre a tooltip."""
    deslizar_mouse(cx, cy)
    if WIGGLE_PX:
        for dx, dy in ((WIGGLE_PX, 0), (-WIGGLE_PX, 0), (0, WIGGLE_PX), (0, 0)):
            mover_mouse(cx + dx, cy + dy)
            time.sleep(0.02)


def slot_bbox(linha, coluna, gx=GRADE_X, gy=GRADE_Y):
    """Retorna (x1, y1, x2, y2) do slot numa grade de origem (gx, gy)."""
    x1 = gx + coluna * PASSO_X
    y1 = gy + linha * PASSO_Y
    return x1, y1, x1 + SLOT_W, y1 + SLOT_H


def slot_centro(linha, coluna, gx=GRADE_X, gy=GRADE_Y):
    """Retorna (x, y) do centro do slot — usado para clicar/mover."""
    x1, y1, x2, y2 = slot_bbox(linha, coluna, gx, gy)
    return (x1 + x2) // 2, (y1 + y2) // 2


# Slot VAZIO = miolo escuro e sem cor; OCUPADO tem ícone (claro ou colorido).
VAZIO_BRILHO = 30   # brilho médio (0-255) abaixo disto = candidato a vazio
VAZIO_SATUR = 25    # saturação média abaixo disto (junto do brilho) = vazio
# Calibração (medida no jogo): VAZIO lê b<=23 e s=0; OCUPADO lê b>=50 e s>=34.
# Há um abismo entre 23 e 50, então brilho<30 E satur<25 separa com folga grande.


def slot_vazio(tela, linha, coluna, gx=GRADE_X, gy=GRADE_Y):
    """True se o slot está vazio (sem item), olhando a imagem 'tela' (captura)."""
    x1, y1, x2, y2 = slot_bbox(linha, coluna, gx, gy)
    crop = tela[y1 + 4:y2 - 4, x1 + 4:x2 - 4]  # miolo, evita a borda do slot
    if crop.size == 0:
        return True
    brilho = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY).mean()
    satur = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)[:, :, 1].mean()
    return brilho < VAZIO_BRILHO and satur < VAZIO_SATUR


_TELA_W = _display.screen().width_in_pixels
_TELA_H = _display.screen().height_in_pixels
_janela_cache = None  # (win, ox, oy, w, h)


def _origem_abs(w):
    """Posição absoluta (x, y) de uma janela, somando geometrias até a raiz."""
    x = y = 0
    while w.id != _root.id:
        g = w.get_geometry()
        x += g.x
        y += g.y
        w = w.query_tree().parent
    return x, y


def localizar_janela(forcar=False):
    """Acha a janela do jogo pelo nome e devolve (win, ox, oy, w, h)."""
    global _janela_cache
    if _janela_cache is not None and not forcar:
        return _janela_cache

    alvo = JANELA_NOME.lower()
    achada = None

    def varrer(w):
        nonlocal achada
        if achada is not None:
            return
        try:
            filhos = w.query_tree().children
        except Exception:
            filhos = []
        for c in filhos:
            try:
                nome = c.get_wm_name()
            except Exception:
                nome = None
            if nome and alvo in nome.lower():
                achada = c
                return
            varrer(c)

    varrer(_root)
    if achada is None:
        raise RuntimeError(f"Janela do jogo '{JANELA_NOME}' não encontrada. "
                           f"Ela está aberta? Ajuste JANELA_NOME.")
    g = achada.get_geometry()
    ox, oy = _origem_abs(achada)
    _janela_cache = (achada, ox, oy, g.width, g.height)
    return _janela_cache


def janela_origem():
    """(x, y) absolutos do canto superior-esquerdo da janela do jogo."""
    _, ox, oy, _, _ = localizar_janela()
    return ox, oy


def capturar_tela():
    """Captura SÓ a janela do jogo e a posiciona numa tela preta do tamanho do
    monitor, mantendo as coordenadas de tela (assim grade/mouse/diff seguem
    iguais). Tudo fora da janela fica preto -> não entra no diff."""
    win, ox, oy, w, h = localizar_janela()
    raw = win.get_image(0, 0, w, h, X.ZPixmap, 0xffffffff)
    janela = np.frombuffer(raw.data, dtype=np.uint8).reshape(h, w, 4)
    janela = cv2.cvtColor(janela, cv2.COLOR_BGRA2BGR)

    canvas = np.zeros((_TELA_H, _TELA_W, 3), dtype=np.uint8)
    # recorta caso a janela passe das bordas
    x0, y0 = max(ox, 0), max(oy, 0)
    x1, y1 = min(ox + w, _TELA_W), min(oy + h, _TELA_H)
    if x1 > x0 and y1 > y0:
        canvas[y0:y1, x0:x1] = janela[y0 - oy:y1 - oy, x0 - ox:x1 - ox]
    return canvas


def capturar_regiao(x1, y1, x2, y2):
    """Captura SÓ o retângulo de TELA (x1,y1)-(x2,y2) da janela do jogo. Muito
    mais rápido que capturar_tela (não pega a janela inteira). Devolve BGR de
    tamanho (y2-y1, x2-x1), em coords de tela (fora da janela = preto)."""
    win, ox, oy, w, h = localizar_janela()
    x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
    out = np.zeros((max(y2 - y1, 0), max(x2 - x1, 0), 3), dtype=np.uint8)
    rx1, ry1 = max(x1 - ox, 0), max(y1 - oy, 0)
    rx2, ry2 = min(x2 - ox, w), min(y2 - oy, h)
    if rx2 <= rx1 or ry2 <= ry1 or out.size == 0:
        return out
    raw = win.get_image(rx1, ry1, rx2 - rx1, ry2 - ry1, X.ZPixmap, 0xffffffff)
    reg = np.frombuffer(raw.data, dtype=np.uint8).reshape(ry2 - ry1, rx2 - rx1, 4)
    reg = cv2.cvtColor(reg, cv2.COLOR_BGRA2BGR)
    dx, dy = (ox + rx1) - x1, (oy + ry1) - y1      # onde a janela cai dentro do out
    out[dy:dy + (ry2 - ry1), dx:dx + (rx2 - rx1)] = reg
    return out


def ocr_imagem(img):
    """Roda OCR numa imagem (amplia antes) e devolve o texto lido (string)."""
    if img is None or img.size == 0:
        return ""
    if ESCALA_OCR != 1:
        img = cv2.resize(img, None, fx=ESCALA_OCR, fy=ESCALA_OCR,
                         interpolation=cv2.INTER_CUBIC)
    resultado, _ = _ocr(img)
    if not resultado:
        return ""
    # resultado: lista de [caixa, texto, confianca]
    return " ".join(item[1] for item in resultado).strip()


def ocr_regiao(x1, y1, x2, y2):
    """Captura o retângulo de tela (x1,y1)-(x2,y2) da janela e devolve o texto
    OCR. Útil para ler headers/dropdowns da UI."""
    return ocr_imagem(capturar_regiao(x1, y1, x2, y2))


def ler_texto(slot_img):
    """Roda OCR num recorte de slot (usando AREA_TEXTO) e devolve a string."""
    x1f, y1f, x2f, y2f = AREA_TEXTO
    h, w = slot_img.shape[:2]
    rec = slot_img[int(h * y1f):int(h * y2f), int(w * x1f):int(w * x2f)]
    return ocr_imagem(rec)


def faixa_nome(cx, ref_y=GRADE_Y, faixa_x=None):
    """Região (x1,y1,x2,y2) onde procurar o NOME/tooltip, numa faixa Y a partir
    de ref_y. O X pode ser:
      - relativo ao centro do slot (padrão, NOME_DX) — bom para o STASH; ou
      - fixo, via faixa_x=(x1,x2) — para o baú, cujo painel abre em zona fixa."""
    _, ox, _oy, ww, _hh = localizar_janela()
    if faixa_x is not None:
        x1, x2 = faixa_x
        x2 = min(x2, ox + ww)
    else:
        x1 = cx + NOME_DX[0]
        x2 = min(cx + NOME_DX[1], ox + ww)
    y1 = ref_y + NOME_DY[0]
    y2 = ref_y + NOME_DY[1]
    return x1, y1, x2, y2


def _eh_nome(txt):
    """True se a linha parece um NOME (não é raridade nem ruído curto)."""
    t = txt.strip()
    if len(t) < 3:
        return False
    low = t.lower()
    return not any(p in low for p in PALAVRAS_IGNORAR)


def _agrupar_linhas(caixas, tol=12, gap_x=45):
    """Junta caixas de OCR na MESMA linha (Y próximo), mas SEPARA segmentos
    quando há um vão horizontal grande (> gap_x) entre eles — isso distingue
    dois tooltips lado a lado (item mirado x item equipado), que ficam no mesmo
    Y. Cada caixa é (topo_y, x1, x2, txt). Devolve linhas (topo_y, x1, x2, texto)
    ordenadas por Y; palavras de um mesmo nome (vão pequeno) ficam juntas."""
    grupos = []
    for c in sorted(caixas, key=lambda b: b[0]):
        for g in grupos:
            if abs(g[0] - c[0]) <= tol:
                g[1].append(c)
                break
        else:
            grupos.append([c[0], [c]])

    saida = []
    for topo, itens in grupos:
        itens.sort(key=lambda b: b[1])  # por X
        # quebra a linha em segmentos onde o vão entre caixas é grande
        segmentos = [[itens[0]]]
        for prev, atual in zip(itens, itens[1:]):
            if atual[1] - prev[2] > gap_x:
                segmentos.append([atual])
            else:
                segmentos[-1].append(atual)

        for seg in segmentos:
            texto = ""
            ult_x2 = None
            for _y, x1, x2, t in seg:
                if texto and (ult_x2 is None or x1 - ult_x2 > 5):
                    texto += " "
                texto += t
                ult_x2 = x2
            sx1 = min(i[1] for i in seg)
            sx2 = max(i[2] for i in seg)
            saida.append((topo, sx1, sx2, texto.strip()))
    saida.sort()
    return saida


def _aguardar_tooltip(base_reg, box):
    """Espera ADAPTATIVA usando capturas SÓ da REGIÃO do nome (baratas): para
    quando a região está PRESENTE (difere da base) e ESTÁVEL (2 capturas seguidas
    quase iguais), ou até estourar ATRASO_HOVER. Devolve a última captura da
    região. Em vez de sleep fixo, para assim que o jogo desenhou o tooltip."""
    x1, y1, x2, y2 = box
    time.sleep(ATRASO_MIN)
    ant = capturar_regiao(x1, y1, x2, y2)
    t0 = time.time()
    while time.time() - t0 < ATRASO_HOVER:
        time.sleep(POLL_INTERVALO)
        reg = capturar_regiao(x1, y1, x2, y2)
        if reg.size == 0:
            return reg
        estavel = cv2.absdiff(reg, ant).mean() < TOOLTIP_ESTAVEL
        presente = base_reg is None or cv2.absdiff(reg, base_reg).mean() > TOOLTIP_PRESENCA
        ant = reg
        if estavel and presente:
            break
    return ant


def ler_item_por_hover(linha, coluna, gx=GRADE_X, gy=GRADE_Y, ref_y=GRADE_Y,
                       faixa_x=None, salvar_debug=False, prefixo_debug="hover",
                       base=None):
    """Passa o mouse no slot (grade de origem gx,gy) e lê o tooltip que aparece.
    O NOME é a linha logo ACIMA da raridade ('... Grade'); ignora o equipado.
    Vazio -> nome "". Devolve (nome, linhas) onde 'linhas' é a lista de linhas
    do tooltip (topo_y, x1, x2, texto), útil para classificar pela tag.

    'base' = captura baseline (mouse FORA, sem tooltip) usada no diff. Se o
    chamador já tem uma (a mesma p/ todos os slots da aba), passe-a para evitar
    uma captura + ida ao descanso por item (metade do tempo, sem perder precisão:
    a UI estática é idêntica entre os slots)."""
    # baseline sem hover (para detectar slot vazio: janela não muda)
    if base is None:
        deslizar_mouse(*ponto_descanso())
        time.sleep(ATRASO_HOVER)
        base = capturar_tela()

    # hover no slot com MOVIMENTO real (deslize + wiggle)
    cx, cy = slot_centro(linha, coluna, gx, gy)
    hover_no_slot(cx, cy)
    fx1, fy1, fx2, fy2 = faixa_nome(cx, ref_y, faixa_x)
    base_reg = base[fy1:fy2, fx1:fx2] if base is not None else None
    # espera adaptativa em cima da REGIÃO (barata); devolve já o recorte do nome
    reg_h = _aguardar_tooltip(base_reg, (fx1, fy1, fx2, fy2))
    # diff só na região (o que apareceu no hover = tooltip); descarta estáticos
    diff_reg = cv2.absdiff(base_reg, reg_h) if base_reg is not None else None

    nome, nome_box, linhas = "", None, []
    if reg_h.size:
        reg = reg_h
        if NOME_ESCALA != 1:
            reg = cv2.resize(reg, None, fx=NOME_ESCALA, fy=NOME_ESCALA,
                             interpolation=cv2.INTER_CUBIC)
        resultado, _ = _ocr(reg)
        caixas = []
        for box, txt, _score in (resultado or []):
            xs = [p[0] / NOME_ESCALA for p in box]
            ys = [p[1] / NOME_ESCALA for p in box]
            bx1, by1 = int(fx1 + min(xs)), int(fy1 + min(ys))
            bx2, by2 = int(fx1 + max(xs)), int(fy1 + max(ys))
            # filtro de diff em coords da REGIÃO (subtrai o offset fx1/fy1)
            if diff_reg is not None:
                rr = diff_reg[by1 - fy1:by2 - fy1, bx1 - fx1:bx2 - fx1]
                if rr.size == 0 or rr.mean() < LINHA_DIFF_MIN:
                    continue
            caixas.append((by1, bx1, bx2, txt.strip()))
        linhas = _agrupar_linhas(caixas)  # ordenadas por Y (cima -> baixo)

        # Sinal estrutural: o NOME é a linha logo ACIMA da 1ª linha de raridade
        # ("... Grade"). Isso ignora cabeçalhos garbleados (STASH->'SUHSH') que
        # ficam mais acima. Sem raridade (alguns materiais): 1ª linha-nome.
        # Quando há 2 tooltips (item mirado + equipado), há 2 candidatos de nome
        # no MESMO Y; escolhemos o do item MIRADO = o mais perto do X do slot.
        def _centro_x(ln):
            return (ln[1] + ln[2]) / 2

        # A raridade ("... Grade") do item MIRADO é a mais perto do X do slot (o
        # tooltip do equipado fica mais longe). O NOME é a linha logo ACIMA dessa
        # raridade E no MESMO tooltip (X alinhado com o da raridade): isso exclui
        # o nome do equipado E fragmentos soltos (ex.: 'ade' de "Rare Grade").
        grades = [ln for ln in linhas if "grade" in ln[3].lower()]
        escolha = None
        if grades:
            grade = min(grades, key=lambda ln: abs(_centro_x(ln) - cx))
            gy, gcx = grade[0], _centro_x(grade)
            acima = [ln for ln in linhas
                     if ln[0] < gy and _eh_nome(ln[3])
                     and abs(_centro_x(ln) - gcx) <= 80]
            if acima:
                escolha = max(acima, key=lambda ln: ln[0])  # mais perto do Grade
        if escolha is None:
            escolha = next((ln for ln in linhas if _eh_nome(ln[3])), None)

        if escolha is not None:
            topo, x1, x2, nome = escolha
            nome_box = (int(x1), int(topo), int(x2), int(topo + 18))

    if salvar_debug:
        os.makedirs(PASTA_DEBUG, exist_ok=True)
        marc = capturar_tela()   # captura cheia só p/ o debug (raro)
        cv2.rectangle(marc, (cx - 20, cy - 20), (cx + 20, cy + 20),
                      (255, 0, 0), 2)                       # azul = slot
        cv2.rectangle(marc, (fx1, fy1), (fx2, fy2), (0, 255, 255), 1)  # amarelo = faixa
        if nome_box is not None:
            cv2.rectangle(marc, nome_box[:2], nome_box[2:], (0, 0, 255), 2)  # verm = nome
        cv2.imwrite(os.path.join(PASTA_DEBUG,
                                 f"{prefixo_debug}_{linha}_{coluna}.png"), marc)
    return nome, linhas


def detectar_por_hover(salvar_debug=False):
    """Percorre toda a grade lendo o nome de cada item via hover/diff."""
    mapa = []
    total = LINHAS * COLUNAS
    n = 0
    for r in range(LINHAS):
        linha_txt = []
        for c in range(COLUNAS):
            n += 1
            texto, _ = ler_item_por_hover(r, c, salvar_debug=salvar_debug)
            linha_txt.append(texto)
            print(f"  [{n}/{total}] slot ({r},{c}) -> {texto or '·'}",
                  flush=True)
        mapa.append(linha_txt)
    mover_mouse(*ponto_descanso())
    return mapa


def detectar():
    """Captura, recorta a grade, faz OCR e devolve matriz de textos."""
    os.makedirs(PASTA_SLOTS, exist_ok=True)
    tela = capturar_tela()
    debug = tela.copy()
    mapa = []

    for r in range(LINHAS):
        linha_txt = []
        for c in range(COLUNAS):
            x1, y1, x2, y2 = slot_bbox(r, c)
            recorte = tela[y1:y2, x1:x2]

            texto = ler_texto(recorte) if recorte.size else ""
            linha_txt.append(texto)

            cv2.imwrite(os.path.join(PASTA_SLOTS, f"slot_{r}_{c}.png"), recorte)

            # desenha o retângulo e o índice no debug
            cv2.rectangle(debug, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(debug, f"{r},{c}", (x1 + 2, y1 + 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)
        mapa.append(linha_txt)

    cv2.imwrite(os.path.join(PASTA, "debug_grade.png"), debug)
    return mapa


def imprimir_mapa(mapa):
    print("\nTexto detectado por slot (linha, coluna):\n")
    larg = max((len(t) for linha in mapa for t in linha), default=4)
    larg = max(larg, 6)
    for r, linha in enumerate(mapa):
        celulas = " | ".join((t or "·").center(larg) for t in linha)
        print(f"  L{r}: {celulas}")
    print("\n-> Confira 'debug_grade.png' para validar o alinhamento da grade.")
    print("-> Recortes individuais em 'slots/'.")


def _uso():
    print("Uso:")
    print("  python inventario.py grade           # só desenha a grade p/ calibrar (não usa hover)")
    print("  python inventario.py hover L C       # testa o hover em UM slot (linha L, coluna C)")
    print("  python inventario.py tudo            # lê TODOS os slots por hover e monta o mapa")
    print("\nAntes de tudo: abra o inventário no jogo e ajuste a config no topo do arquivo.")


if __name__ == "__main__":
    modo = sys.argv[1] if len(sys.argv) > 1 else "tudo"

    if modo == "grade":
        print("Desenhando a grade (sem hover)...")
        mapa = detectar()
        imprimir_mapa(mapa)

    elif modo == "hover":
        if len(sys.argv) < 4:
            _uso()
            sys.exit(1)
        L, C = int(sys.argv[2]), int(sys.argv[3])
        print(f"Testando hover no slot ({L},{C})... não mexa no mouse.")
        texto, linhas = ler_item_por_hover(L, C, salvar_debug=True)
        print(f"Nome lido: {texto or '(nada)'}")
        print("Linhas do tooltip:")
        for topo, x1, x2, t in linhas:
            print(f"   y={topo:.0f}  {t!r}")
        print(f"-> Veja 'debug_hover/hover_{L}_{C}.png' (amarelo = faixa, vermelho = nome).")

    elif modo == "tudo":
        print("Lendo todos os slots por hover... NÃO mexa no mouse durante o processo.\n")
        mapa = detectar_por_hover(salvar_debug=True)
        imprimir_mapa(mapa)

    else:
        _uso()
