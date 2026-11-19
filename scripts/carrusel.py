#!/usr/bin/env python3
"""carrusel-pro · convierte un guion JSON en las imágenes PNG de un carrusel.

Uso:
    python3 carrusel.py guion.json [carpeta_salida]

Solo necesita Pillow (viene en Claude.ai y en casi cualquier Python: pip install pillow).
El guion trae la marca, la plantilla, el formato y las slides. Ver SKILL.md.
"""
import json, math, os, random, sys
from PIL import Image, ImageDraw, ImageFont, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import iconos

AQUI = os.path.dirname(os.path.abspath(__file__))
FUENTES = os.path.join(AQUI, "..", "fuentes")

TAMANOS = {"instagram": (1080, 1350), "tiktok": (1080, 1920)}

# Cada plantilla define fuentes, colores por defecto y cómo se marca el *énfasis*.
PLANTILLAS = {
    "editorial": dict(titulo="InstrumentSerif-Regular.ttf", titulo_it="InstrumentSerif-Italic.ttf",
                      texto="InstrumentSans-Regular.ttf", fuerte="InstrumentSans-Bold.ttf",
                      fondo="#F4EFE6", tinta="#1B1B1B", acento="#C8102E", enfasis="italica",
                      escala_titulo=1.25),
    "minimal": dict(titulo="InstrumentSans-Bold.ttf", titulo_it="InstrumentSans-Bold.ttf",
                    texto="InstrumentSans-Regular.ttf", fuerte="InstrumentSans-Bold.ttf",
                    fondo="#FFFFFF", tinta="#111111", acento="#2F6BFF", enfasis="color",
                    escala_titulo=1.0),
    "bloque": dict(titulo="Poppins-Bold.ttf", titulo_it="Poppins-Bold.ttf",
                   texto="InstrumentSans-Regular.ttf", fuerte="Poppins-Bold.ttf",
                   fondo="#111111", tinta="#FFFFFF", acento="#FF4D2E", enfasis="caja",
                   escala_titulo=0.95),
    "cuaderno": dict(titulo="Kalam-Bold.ttf", titulo_it="Kalam-Bold.ttf",
                     texto="InstrumentSans-Regular.ttf", fuerte="Kalam-Bold.ttf",
                     fondo="#FBF7EE", tinta="#1E2A44", acento="#E63946", enfasis="marcatextos",
                     escala_titulo=1.05),
}


# ---------- utilidades ----------
def hexrgb(h, a=255):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (a,)


def mezcla(c1, c2, t):
    return tuple(int(c1[i] * (1 - t) + c2[i] * t) for i in range(3)) + (255,)


def fuente(nombre, tam):
    ruta = nombre if os.path.isabs(nombre) else os.path.join(FUENTES, nombre)
    return ImageFont.truetype(ruta, int(tam))


def tokens(texto):
    """'Hola *mundo*: bonito' -> [('Hola', False), ('mundo', True), (':', False) pegado, ('bonito', False)].
    Devuelve (palabra, énfasis, pegado_a_la_anterior)."""
    out, previo = [], " "
    for i, trozo in enumerate(texto.split("*")):
        enf = i % 2 == 1
        for k, p in enumerate(trozo.split()):
            pegado = k == 0 and out and not trozo[:1].isspace() and not previo[-1:].isspace()
            out.append((p, enf, bool(pegado)))
        if trozo:
            previo = trozo
    return out


def ancho_linea(l, f, f_it=None, enfasis=None):
    esp = f.getlength(" ")
    tot = 0
    for j, (p, e, peg) in enumerate(l):
        ff = f_it if (f_it and e and enfasis == "italica") else f
        tot += ff.getlength(p) + (0 if (j == 0 or peg) else esp)
    return tot


def lineas(texto, f, ancho):
    """Parte el texto en renglones que caben en `ancho`. Respeta saltos con \\n."""
    res = []
    for parrafo in texto.split("\n"):
        actual, w_act = [], 0
        esp = f.getlength(" ")
        for pal, enf, peg in tokens(parrafo):
            w = f.getlength(pal)
            if actual and not peg and w_act + esp + w > ancho:
                res.append(actual)
                actual, w_act = [], 0
            actual.append((pal, enf, peg and bool(actual)))
            w_act += (esp if len(actual) > 1 and not peg else 0) + w
        res.append(actual)
    return res


def ajusta(texto, nombre_fuente, tam, ancho, alto, interlineado=1.12, minimo=28):
    """Baja el tamaño hasta que el texto quepa en la caja."""
    while tam > minimo:
        f = fuente(nombre_fuente, tam)
        ls = lineas(texto, f, ancho)
        if len(ls) * tam * interlineado <= alto and all(
                ancho_linea(l, f) <= ancho for l in ls):
            return f, ls, tam
        tam -= 4
    f = fuente(nombre_fuente, minimo)
    return f, lineas(texto, f, ancho), minimo


class Lienzo:
    def __init__(self, guion, n, total):
        self.g = guion
        self.formato = guion.get("_formato", "instagram")
        self.W, self.H = TAMANOS[self.formato]
        self.p = dict(PLANTILLAS[guion.get("plantilla", "editorial")])
        # la marca puede traer sus propias tipografías (archivos .ttf/.otf)
        fm = guion.get("marca", {}).get("fuentes", {})
        if fm.get("titulo"):
            self.p["titulo"] = self.p["titulo_it"] = fm["titulo"]
        if fm.get("texto"):
            self.p["texto"] = fm["texto"]
        if fm.get("fuerte") or fm.get("texto"):
            self.p["fuerte"] = fm.get("fuerte", fm.get("texto"))
        colores = guion.get("marca", {}).get("colores", {})
        self.fondo = hexrgb(colores.get("fondo", self.p["fondo"]))
        self.tinta = hexrgb(colores.get("tinta", self.p["tinta"]))
        self.acento = hexrgb(colores.get("acento", self.p["acento"]))
        self.suave = mezcla(self.tinta, self.fondo, 0.45)
        self.n, self.total = n, total
        self.img = Image.new("RGBA", (self.W, self.H), self.fondo)
        self.d = ImageDraw.Draw(self.img)
        # zona segura: en TikTok se evita la interfaz (pestañas arriba, botones a la derecha, descripción abajo)
        if self.formato == "tiktok":
            self.x0, self.x1, self.y0, self.y1 = 90, self.W - 170, 270, 1440
        else:
            self.x0, self.x1, self.y0, self.y1 = 96, self.W - 96, 120, self.H - 150

    def dibujo(self, figuras, caja):
        """Ilustración hecha por Claude para esta slide (ver iconos.py)."""
        if not figuras:
            return
        pal = dict(tinta=self.tinta, acento=self.acento, fondo=self.fondo, suave=self.suave,
                   claro=mezcla(self.acento, self.fondo, 0.72))
        if self.g.get("plantilla") == "bloque":
            pal["claro"] = mezcla(self.acento, self.fondo, 0.55)
            pal["tinta"] = self.tinta
        iconos.dibujar(self.img, figuras, caja, pal, fuente_ttf=os.path.join(FUENTES, self.p["fuerte"]))

    # ----- fondo de cada plantilla -----
    def decorar_fondo(self, invertido=False):
        nombre = self.g.get("plantilla", "editorial")
        if invertido:
            self.d.rectangle([0, 0, self.W, self.H], fill=self.acento if nombre != "bloque" else self.acento)
        if nombre == "cuaderno":
            paso = 46
            punto = mezcla(self.tinta, self.fondo, 0.82)
            for y in range(paso, self.H, paso):
                for x in range(paso, self.W, paso):
                    self.d.ellipse([x - 2, y - 2, x + 2, y + 2], fill=punto)
        elif nombre == "editorial":
            ruido = Image.effect_noise((self.W, self.H), 18).convert("L")
            capa = Image.new("RGBA", (self.W, self.H), self.tinta[:3] + (0,))
            capa.putalpha(ruido.point(lambda v: max(0, v - 118) // 6))
            self.img.alpha_composite(capa)
            self.d.line([self.x0, self.y0 - 30, self.x1, self.y0 - 30], fill=self.tinta, width=2)
        elif nombre == "bloque" and not invertido:
            self.d.rectangle([0, 0, 22, self.H], fill=self.acento)

    # ----- texto con énfasis -----
    def texto(self, texto, caja, nombre_fuente, tam, color=None, alinear="izq", interlineado=1.12,
              enfasis=None, vertical="arriba", minimo=28):
        x0, y0, x1, y1 = caja
        color = color or self.tinta
        enfasis = enfasis or self.p["enfasis"]
        f, ls, tam = ajusta(texto, nombre_fuente, tam, x1 - x0, y1 - y0, interlineado, minimo)
        f_it = fuente(self.p["titulo_it"], tam) if nombre_fuente == self.p["titulo"] else f
        alto = len(ls) * tam * interlineado
        y = y0 if vertical == "arriba" else (y0 + (y1 - y0 - alto) / 2 if vertical == "centro" else y1 - alto)
        esp = f.getlength(" ")
        for l in ls:
            anchos = [(f_it if (e and enfasis == "italica") else f).getlength(p) for p, e, _ in l]
            total = ancho_linea(l, f, f_it, enfasis)
            x = x0 if alinear == "izq" else (x0 + (x1 - x0 - total) / 2 if alinear == "centro" else x1 - total)
            pos, xx = [], x
            for j, ((p, e, peg), w) in enumerate(zip(l, anchos)):
                if j and not peg:
                    xx += esp
                pos.append(xx)
                xx += w
            # primero los fondos del énfasis (para que no tapen letras vecinas)
            for (p, e, peg), w, xx in zip(l, anchos, pos):
                if e and enfasis == "marcatextos":
                    capa = Image.new("RGBA", self.img.size, (0, 0, 0, 0))
                    ImageDraw.Draw(capa).rounded_rectangle(
                        [xx - 6, y + tam * 0.48, xx + w + 6, y + tam * 0.98], radius=8, fill=self.acento[:3] + (90,))
                    self.img.alpha_composite(capa)
                elif e and enfasis == "caja":
                    bx = self.d.textbbox((xx, y), "Hgy", font=f)
                    self.d.rectangle([xx - 10, bx[1] - 8, xx + w + 10, bx[3] + 8], fill=self.acento)
            for (p, e, peg), w, xx in zip(l, anchos, pos):
                ff = f_it if (e and enfasis == "italica") else f
                c = color
                if e and enfasis in ("color", "italica"):
                    c = self.acento
                if e and enfasis == "caja":
                    c = self.fondo if self.g.get("plantilla") != "bloque" else (17, 17, 17, 255)
                if e and enfasis == "subrayado":
                    bx = self.d.textbbox((xx, y), p, font=ff)
                    self.d.line([xx, bx[3] + 10, xx + w, bx[3] + 10], fill=c, width=int(max(4, tam // 18)))
                self.d.text((xx, y), p, font=ff, fill=c)
            y += tam * interlineado
        return y  # dónde terminó el texto

    # ----- pie: @usuario, número de slide, "desliza" -----
    def pie(self, desliza=False, color=None):
        color = color or self.suave
        m = self.g.get("marca", {})
        f = fuente(self.p["fuerte"], 30)
        yb = self.y1 + 60 if self.formato == "instagram" else self.y1 + 20
        usuario = m.get("usuario", "")
        logo = m.get("logo")
        x = self.x0
        if logo and os.path.exists(logo):
            lg = Image.open(logo).convert("RGBA")
            lg.thumbnail((140, 52))
            self.img.alpha_composite(lg, (int(x), int(yb - lg.height / 2 + 14)))
            x += lg.width + 18
        if usuario:
            self.d.text((x, yb), usuario, font=f, fill=color)
        if desliza:
            t = "Desliza"
            ca = self.acento if color == self.suave else color
            xa = self.x1 - 44
            self.d.text((xa - 16 - f.getlength(t), yb), t, font=f, fill=ca)
            ym = yb + 20
            self.d.line([xa, ym, xa + 40, ym], fill=ca, width=4)
            self.d.line([xa + 26, ym - 12, xa + 40, ym, xa + 26, ym + 12], fill=ca, width=4, joint="curve")
        else:
            t = f"{self.n}/{self.total}"
            self.d.text((self.x1 - f.getlength(t), yb), t, font=f, fill=color)

    def foto(self, ruta, caja, radio=28):
        if not ruta or not os.path.exists(ruta):
            return False
        x0, y0, x1, y1 = [int(v) for v in caja]
        im = Image.open(ruta).convert("RGBA")
        w, h = x1 - x0, y1 - y0
        esc = max(w / im.width, h / im.height)
        im = im.resize((math.ceil(im.width * esc), math.ceil(im.height * esc)), Image.LANCZOS)
        l, t = (im.width - w) // 2, (im.height - h) // 2
        im = im.crop((l, t, l + w, t + h))
        mascara = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mascara).rounded_rectangle([0, 0, w, h], radius=radio, fill=255)
        self.img.paste(im, (x0, y0), mascara)
        return True


# ---------- tipos de slide ----------
def s_portada(c, s):
    plant = c.g.get("plantilla")
    inv = plant == "bloque"
    c.decorar_fondo()
    tinta = c.tinta
    y = c.y0
    if s.get("etiqueta"):
        f = fuente(c.p["fuerte"], 32)
        t = s["etiqueta"].upper()
        w = f.getlength(t)
        c.d.rounded_rectangle([c.x0, y, c.x0 + w + 44, y + 60], radius=30, outline=c.acento, width=3)
        c.d.text((c.x0 + 22, y + 10), t, font=f, fill=c.acento)
        y += 110
    tiene_foto = bool(s.get("foto")) and os.path.exists(s.get("foto", ""))
    tiene_dibujo = bool(s.get("dibujo")) and not tiene_foto
    alto_titulo = (c.y1 - y) * (0.48 if tiene_foto else (0.42 if tiene_dibujo else 0.78))
    fin = c.texto(s["titulo"], (c.x0, y, c.x1, y + alto_titulo), c.p["titulo"],
                  150 * c.p["escala_titulo"], tinta, interlineado=1.02,
                  vertical="arriba" if (tiene_foto or tiene_dibujo) else "centro")
    if s.get("subtitulo"):
        fin = c.texto(s["subtitulo"], (c.x0, fin + 56, c.x1, fin + 286), c.p["texto"], 44, c.suave,
                      enfasis="color", interlineado=1.3)
    if tiene_foto:
        c.foto(s["foto"], (c.x0, fin + 40, c.x1, c.y1 - 10))
    elif tiene_dibujo:
        c.dibujo(s["dibujo"], (c.x0 - 40, fin + 20, c.x1 + 40, c.y1 - 10))
    c.pie(desliza=True)


def s_punto(c, s):
    c.decorar_fondo()
    y = c.y0
    num = s.get("num")
    if num is not None:
        f = fuente(c.p["titulo_it"] if c.g.get("plantilla") == "editorial" else c.p["titulo"], 230)
        t = f"{num:02d}" if isinstance(num, int) else str(num)
        c.d.text((c.x0 - 6, y - 70), t, font=f, fill=c.acento)
        y += 200
    if s.get("dibujo"):
        lado = 300 if c.formato == "instagram" else 330
        c.dibujo(s["dibujo"], (c.x1 - lado, c.y0 - 20, c.x1, c.y0 - 20 + lado))
        y = max(y, c.y0 + lado + 10)
    fin = c.texto(s["titulo"], (c.x0, y, c.x1, y + 330), c.p["titulo"], 108 * c.p["escala_titulo"],
                  interlineado=1.05)
    c.d.line([c.x0, fin + 34, c.x0 + 120, fin + 34], fill=c.acento, width=6)
    if s.get("texto"):
        c.texto(s["texto"], (c.x0, fin + 80, c.x1, c.y1 - 20), c.p["texto"], 56, c.suave,
                enfasis="color", interlineado=1.38)
    c.pie()


def s_lista(c, s):
    c.decorar_fondo()
    xt = c.x1
    if s.get("dibujo"):
        c.dibujo(s["dibujo"], (c.x1 - 240, c.y0 - 10, c.x1, c.y0 + 230))
        xt = c.x1 - 270
    fin = c.texto(s["titulo"], (c.x0, c.y0, xt, c.y0 + 300), c.p["titulo"], 90 * c.p["escala_titulo"],
                  interlineado=1.05)
    items = s.get("items", [])
    y = max(fin + 60, c.y0 + 270) if s.get("dibujo") else fin + 60
    alto = min((c.y1 - y) / max(1, len(items)), 210)
    for i, it in enumerate(items):
        r = 26
        cy = y + 40
        if s.get("marca") == "check" or c.g.get("plantilla") == "cuaderno":
            c.d.line([c.x0, cy, c.x0 + 16, cy + 18, c.x0 + 44, cy - 20], fill=c.acento, width=8, joint="curve")
        else:
            c.d.ellipse([c.x0, cy - r, c.x0 + 2 * r, cy + r], fill=c.acento)
            f = fuente(c.p["fuerte"], 30)
            t = str(i + 1)
            c.d.text((c.x0 + r - f.getlength(t) / 2, cy - 20), t, font=f, fill=c.fondo)
        c.texto(it, (c.x0 + 80, y + 8, c.x1, y + alto - 16), c.p["texto"], 48, enfasis="color",
                interlineado=1.25, minimo=30)
        y += alto
    c.pie()


def s_dato(c, s):
    c.decorar_fondo()
    if s.get("dibujo"):
        c.dibujo(s["dibujo"], (c.x0, c.y0, c.x0 + 280, c.y0 + 280))
    zona = (c.y1 - c.y0)
    fin = c.texto(s["cifra"], (c.x0, c.y0 + zona * 0.12, c.x1, c.y0 + zona * 0.5), c.p["titulo"], 300,
                  c.acento, interlineado=1.0, enfasis="color", vertical="abajo")
    fin = c.texto(s["texto"], (c.x0, fin + 40, c.x1, fin + 420), c.p["fuerte"], 62, interlineado=1.18)
    if s.get("fuente"):
        c.texto("Fuente: " + s["fuente"], (c.x0, c.y1 - 70, c.x1, c.y1), c.p["texto"], 28, c.suave,
                vertical="abajo")
    c.pie()


def s_cita(c, s):
    c.decorar_fondo()
    f = fuente("InstrumentSerif-Regular.ttf", 340)
    c.d.text((c.x0 - 10, c.y0 - 90), "“", font=f, fill=c.acento)
    fin = c.texto(s["texto"], (c.x0, c.y0 + 200, c.x1, c.y1 - 160), c.p["titulo"],
                  86 * c.p["escala_titulo"], interlineado=1.12, vertical="centro")
    if s.get("autor"):
        c.texto("— " + s["autor"], (c.x0, fin + 30, c.x1, fin + 100), c.p["fuerte"], 36, c.suave)
    c.pie()


def s_antes_despues(c, s):
    c.decorar_fondo()
    fin = c.texto(s.get("titulo", ""), (c.x0, c.y0, c.x1, c.y0 + 240), c.p["titulo"],
                  84 * c.p["escala_titulo"], interlineado=1.05)
    y = fin + 50
    mitad = (c.y1 - y - 30) / 2
    for i, (eti, txt) in enumerate([(s.get("eti_antes", "Antes"), s["antes"]),
                                    (s.get("eti_despues", "Después"), s["despues"])]):
        caja = [c.x0, y, c.x1, y + mitad]
        relleno = mezcla(c.tinta, c.fondo, 0.93) if i == 0 else mezcla(c.acento, c.fondo, 0.86)
        c.d.rounded_rectangle(caja, radius=28, fill=relleno)
        f = fuente(c.p["fuerte"], 32)
        c.d.text((c.x0 + 36, y + 28), eti.upper(), font=f, fill=c.suave if i == 0 else c.acento)
        c.texto(txt, (c.x0 + 36, y + 84, c.x1 - 36, y + mitad - 28), c.p["texto"], 46, enfasis="color",
                interlineado=1.3)
        y += mitad + 30
    c.pie()


def s_cierre(c, s):
    plant = c.g.get("plantilla")
    c.img.paste(Image.new("RGBA", c.img.size, c.acento if plant != "bloque" else c.acento), (0, 0))
    c.d = ImageDraw.Draw(c.img)
    claro = c.fondo if plant != "bloque" else (17, 17, 17, 255)
    if s.get("dibujo"):
        c.acento, c.fondo = claro, c.acento  # en el cierre el dibujo va en el color claro
        c.dibujo(s["dibujo"], (c.x0, c.y0, c.x0 + 300, c.y0 + 300))
        c.acento, c.fondo = c.fondo, claro
    fin = c.texto(s["titulo"], (c.x0, c.y0 + (320 if s.get("dibujo") else 0), c.x1, c.y0 + (c.y1 - c.y0) * 0.6), c.p["titulo"],
                  120 * c.p["escala_titulo"], claro, interlineado=1.08, enfasis="subrayado", vertical="centro")
    if s.get("cta"):
        f = fuente(c.p["fuerte"], 40)
        t = s["cta"]
        w = f.getlength(t)
        y = fin + 70
        c.d.rounded_rectangle([c.x0, y, c.x0 + w + 80, y + 96], radius=48, fill=claro)
        c.d.text((c.x0 + 40, y + 22), t, font=f, fill=c.acento)
    c.pie(color=claro)


TIPOS = dict(portada=s_portada, punto=s_punto, lista=s_lista, dato=s_dato, cita=s_cita,
             antes_despues=s_antes_despues, cierre=s_cierre)


def render(guion, salida):
    os.makedirs(salida, exist_ok=True)
    formatos = guion.get("formato", "instagram")
    formatos = ["instagram", "tiktok"] if formatos == "ambos" else [formatos]
    rutas = []
    for fmt in formatos:
        g = dict(guion, _formato=fmt)
        slides = guion["slides"]
        carpeta = os.path.join(salida, fmt) if len(formatos) > 1 else salida
        os.makedirs(carpeta, exist_ok=True)
        for i, s in enumerate(slides, 1):
            c = Lienzo(g, i, len(slides))
            TIPOS[s.get("tipo", "punto")](c, s)
            ruta = os.path.join(carpeta, f"{i:02d}.png")
            c.img.convert("RGB").save(ruta, optimize=True)
            rutas.append(ruta)
        # hoja de contacto para revisar todo de un vistazo
        ims = [Image.open(r) for r in rutas[-len(slides):]]
        tw = 360
        th = int(tw * ims[0].height / ims[0].width)
        cols = min(4, len(ims))
        filas = math.ceil(len(ims) / cols)
        hoja = Image.new("RGB", (cols * tw + (cols + 1) * 20, filas * th + (filas + 1) * 20), (230, 230, 230))
        for k, im in enumerate(ims):
            hoja.paste(im.resize((tw, th), Image.LANCZOS), (20 + (k % cols) * (tw + 20), 20 + (k // cols) * (th + 20)))
        hoja.save(os.path.join(carpeta, "_revision.jpg"), quality=85)
    return rutas


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    with open(sys.argv[1], encoding="utf-8") as fh:
        guion = json.load(fh)
    salida = sys.argv[2] if len(sys.argv) > 2 else guion.get("salida", "carrusel")
    base = os.path.dirname(os.path.abspath(sys.argv[1]))
    # rutas relativas (logo, fotos) se buscan junto al guion
    m = guion.get("marca", {})
    if m.get("logo") and not os.path.isabs(m["logo"]):
        m["logo"] = os.path.join(base, m["logo"])
    for k, v in m.get("fuentes", {}).items():
        if v and not os.path.isabs(v):
            m["fuentes"][k] = os.path.join(base, v)
    for s in guion["slides"]:
        if s.get("foto") and not os.path.isabs(s["foto"]):
            s["foto"] = os.path.join(base, s["foto"])
    for r in render(guion, salida):
        print(r)
