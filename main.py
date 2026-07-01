"""
Movimentação de mouse para o jogo TaskbarHero.

Ciclo: vai de A para B e clica, volta para A e clica, e por fim vai para C
e clica. Repete.

Usa python-xlib + extensão XTEST para gerar eventos de mouse "reais"
(detectados melhor por jogos do que um simples reposicionamento do cursor).
Não precisa de nenhuma biblioteca/pacote de sistema além do python3-Xlib.
Só funciona em sessões X11 (não Wayland).

Como usar:
  1. Descubra as coordenadas dos pontos rodando o modo de captura:
         python main.py pos
     Mova o mouse onde quiser e leia as coordenadas no terminal. Ctrl+C sai.

  2. Ajuste PONTO_A e PONTO_B abaixo com as coordenadas anotadas.

  3. Rode o script:
         python main.py
     Há uma contagem regressiva: foque a janela do jogo antes de começar.

1612 561
1737 561

Para abortar: Ctrl+C no terminal. (Defina também REPETICOES para parar sozinho.)
"""

import sys
import time

from Xlib import X, display
from Xlib.ext import xtest

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO — ajuste aqui
# ---------------------------------------------------------------------------
PONTO_A = (1612, 561)      # (x, y) do ponto A
PONTO_B = (1737, 561)      # (x, y) do ponto B
PONTO_C = (1615, 507)      # (x, y) do ponto C (clicado por último)
BOTAO = 1                 # 1 = esquerdo, 2 = meio, 3 = direito

DURACAO_MOVIMENTO = 2  # segundos para deslizar o mouse de um ponto a outro
PASSOS_MOVIMENTO = 25     # nº de passos no deslize (mais = mais suave)
PAUSA_APOS_CLIQUE = 1  # segundos de espera depois de cada clique
PAUSA_ENTRE_CICLOS = 300 # segundos entre o fim de um ciclo e o começo do outro
REPETICOES = 0            # 0 = infinito; ou um número de ciclos
CONTAGEM_INICIAL = 5      # segundos de contagem regressiva antes de iniciar
# ---------------------------------------------------------------------------

_display = display.Display()
_root = _display.screen().root


def posicao_atual():
    """Retorna (x, y) atual do ponteiro."""
    dados = _root.query_pointer()._data
    return dados["root_x"], dados["root_y"]


def mover_para(x, y):
    """Move o ponteiro para a posição absoluta (x, y)."""
    xtest.fake_input(_display, X.MotionNotify, x=int(x), y=int(y))
    _display.sync()


def deslizar(destino, duracao, passos):
    """Move suavemente do ponto atual até 'destino'."""
    x0, y0 = posicao_atual()
    x1, y1 = destino
    passos = max(1, passos)
    for i in range(1, passos + 1):
        t = i / passos
        mover_para(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
        time.sleep(duracao / passos)
    mover_para(x1, y1)


def clicar(botao=BOTAO):
    """Pressiona e solta o botão do mouse na posição atual."""
    xtest.fake_input(_display, X.ButtonPress, botao)
    _display.sync()
    xtest.fake_input(_display, X.ButtonRelease, botao)
    _display.sync()


def ir_clicar(ponto):
    """Desliza até o ponto e clica."""
    deslizar(ponto, DURACAO_MOVIMENTO, PASSOS_MOVIMENTO)
    clicar()
    time.sleep(PAUSA_APOS_CLIQUE)


def mostrar_posicao():
    """Imprime a posição do mouse em tempo real para descobrir coordenadas."""
    print("Mova o mouse. Pressione Ctrl+C para sair.\n")
    try:
        while True:
            x, y = posicao_atual()
            print(f"  X: {x:>5}   Y: {y:>5}", end="\r", flush=True)
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("\nEncerrado.")


def loop_principal():
    print(f"Ponto A: {PONTO_A}   Ponto B: {PONTO_B}   Ponto C: {PONTO_C}   Botão: {BOTAO}")
    print(f"Repetições: {'infinito' if REPETICOES == 0 else REPETICOES}")
    print("Para abortar: Ctrl+C no terminal.\n")

    for s in range(CONTAGEM_INICIAL, 0, -1):
        print(f"Começando em {s}...", end="\r", flush=True)
        time.sleep(1)
    print("Iniciado!            \n")

    ciclo = 0
    try:
        while REPETICOES == 0 or ciclo < REPETICOES:
            ciclo += 1

            ir_clicar(PONTO_A)
            ir_clicar(PONTO_B)
            ir_clicar(PONTO_C)
            print(f"Ciclo {ciclo} concluído", end="\r", flush=True)
            time.sleep(PAUSA_ENTRE_CICLOS)
    except KeyboardInterrupt:
        print("\nInterrompido pelo usuário.")
    finally:
        print(f"\nTotal de ciclos: {ciclo}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("pos", "posicao", "position"):
        mostrar_posicao()
    else:
        loop_principal()
