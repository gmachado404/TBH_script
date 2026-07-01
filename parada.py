"""
Tecla de parada GLOBAL (Alt+ç) via X11.

Registra um atalho global (XGrabKey na janela raiz) numa thread dedicada: ao
pressionar Alt+ç em QUALQUER janela, marca o evento `parar` e levanta um
KeyboardInterrupt na thread principal — o mesmo efeito de um Ctrl+C no terminal,
mas sem precisar focar o terminal. Usa uma conexão X própria (Xlib não é
thread-safe p/ compartilhar a mesma conexão).
"""
import _thread
import threading

from Xlib import X, XK, display

parar = threading.Event()   # setado quando Alt+ç é pressionado

_instalado = False


def _listener(disp, root, keycode):
    while True:
        try:
            ev = disp.next_event()
        except Exception:
            return
        if ev.type == X.KeyPress and ev.detail == keycode:
            parar.set()
            _thread.interrupt_main()   # = Ctrl+C na thread principal


def instalar(verbose=True):
    """Liga o atalho global Alt+ç. Devolve True se conseguiu. Em qualquer falha
    (sem X, tecla já capturada, etc.) avisa e segue — o Ctrl+C continua valendo."""
    global _instalado
    if _instalado:
        return True
    try:
        disp = display.Display()
        root = disp.screen().root
        keycode = disp.keysym_to_keycode(XK.string_to_keysym("ccedilla"))
        if not keycode:
            if verbose:
                print("  (parada global: não achei a tecla ç — use Ctrl+C)",
                      flush=True)
            return False
        # Mod1 = Alt. Grava também com Lock(CapsLock)/Mod2(NumLock) p/ robustez.
        mod = X.Mod1Mask
        for extra in (0, X.LockMask, X.Mod2Mask, X.LockMask | X.Mod2Mask):
            root.grab_key(keycode, mod | extra, True,
                          X.GrabModeAsync, X.GrabModeAsync)
        disp.sync()
        t = threading.Thread(target=_listener, args=(disp, root, keycode),
                             daemon=True)
        t.start()
        _instalado = True
        if verbose:
            print("  parada global ativa: Alt+ç (em qualquer janela).",
                  flush=True)
        return True
    except Exception as e:
        if verbose:
            print(f"  (parada global indisponível: {e!r} — use Ctrl+C)",
                  flush=True)
        return False
