"""Cartaz do jogo: o fiorde ao pôr do sol renderizado no Cycles.

Usa o mesmo relevo do jogo (ruído portado de index.html, mesma semente), os
marcos com os materiais procedurais completos e o planador reconstruído a
partir do código three.js. Chamado por cenario.py com --cartaz.
"""
import math

import bpy
import numpy as np
from mathutils import Vector

from cenario import Malha, rad, simples

SUN_ELEV, SUN_AZ = 5.0, 200  # graus, na convenção do jogo (three.js)
CEU = 0.12  # o Nishita vem em escala física; põe céu e névoa na escala da lâmpada do sol


def T(x, y, z):
    """three.js (y para cima, voo para -z) → Blender (z para cima)."""
    return Vector((x, -z, y))


# ============================================================ relevo (porte de index.html)
def _perm():
    s = 1337
    def rnd():
        nonlocal s
        s = (s + 0x6D2B79F5) & 0xFFFFFFFF
        t = ((s ^ (s >> 15)) * (1 | s)) & 0xFFFFFFFF
        t = ((t + (((t ^ (t >> 7)) * (61 | t)) & 0xFFFFFFFF)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296
    p = list(range(256))
    for i in range(255, 0, -1):
        j = int(rnd() * (i + 1))
        p[i], p[j] = p[j], p[i]
    return np.array(p + p, dtype=np.int64)


PERM = _perm()


def vnoise(x, y):
    xi, yi = np.floor(x), np.floor(y)
    xf, yf = x - xi, y - yi
    u, v = xf * xf * (3 - 2 * xf), yf * yf * (3 - 2 * yf)
    X, Y = xi.astype(np.int64) & 255, yi.astype(np.int64) & 255
    P = PERM
    a, b = P[X + P[Y]] / 255, P[X + 1 + P[Y]] / 255
    c, d = P[X + P[Y + 1]] / 255, P[X + 1 + P[Y + 1]] / 255
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v


def fbm2(x, y, oct):
    s, a, f = 0.0, 0.5, 1.0
    for _ in range(oct):
        s = s + a * vnoise(x * f, y * f)
        f *= 2.03
        a *= 0.5
    return s


def ridged(x, y, oct):
    s, a, f = 0.0, 0.5, 1.0
    for _ in range(oct):
        n = 1 - np.abs(vnoise(x * f + 31.7, y * f) * 2 - 1)
        s = s + a * n * n
        f *= 2.1
        a *= 0.5
    return s


def smooth(a, b, v):
    t = np.clip((v - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def shore_at(z, lado):
    return 82 + 50 * fbm2(np.asarray(z, float) * 0.0028 + (40 if lado > 0 else 0), np.full(np.shape(z), 7.3), 3)


def fjord_h(x, z):
    ax = np.abs(x)
    shore = 82 + 50 * fbm2(z * 0.0028 + np.where(x > 0, 40, 0), np.full_like(x, 7.3), 3)
    d = ax - shore
    det = (fbm2(x * 0.035, z * 0.035, 3) - 0.5) * 9
    agua = np.maximum(-40, d * 0.6) + det * 0.3 - 2
    t = np.clip(d / 430, 0, 1)
    rise = 1 - (1 - t) ** 1.8
    peak = 300 + 380 * fbm2(x * 0.0014, z * 0.0014, 4)
    rid = ridged(x * 0.004, z * 0.004, 4) * 160
    far = smooth(600, 1500, ax) * 420
    terra = 12 * smooth(0, 6, d) + rise * (peak + rid) + far + det * (0.5 + rise) - 2
    return np.where(d < 0, agua, terra)


def relevo(patamares):
    u = np.linspace(-1, 1, 321)
    xs = np.sign(u) * np.abs(u) ** 1.7 * 1700
    zs = 150 - 4600 * np.linspace(0, 1, 301) ** 1.5
    X, Z = np.meshgrid(xs, zs)
    H = fjord_h(X, Z)
    for cx, cz, alt in patamares:
        t = 1 - smooth(1, 2.2, np.hypot((X - cx) / 16, (Z - cz) / 24))
        H = H + (alt - H) * t
    ny, nx = H.shape
    verts = np.stack([X.ravel(), -Z.ravel(), H.ravel()], 1)
    i = np.arange(ny - 1)[:, None] * nx + np.arange(nx - 1)[None, :]
    quads = np.stack([i, i + 1, i + nx + 1, i + nx], -1).reshape(-1, 4)
    me = bpy.data.meshes.new('Relevo')
    me.from_pydata(verts.tolist(), [], quads.tolist())
    me.shade_smooth()
    ob = bpy.data.objects.new('Relevo', me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


# ============================================================ materiais do cenário
def _no(nt, tipo, **props):
    n = nt.nodes.new(tipo)
    for k, v in props.items():
        setattr(n, k, v)
    return n


def _ceu(nt, disco=True):
    sky = _no(nt, 'ShaderNodeTexSky', sky_type='NISHITA', sun_disc=disco, sun_elevation=rad(SUN_ELEV),
              sun_rotation=_rot_sol(), air_density=1.0, dust_density=3.0, ozone_density=1.0, sun_size=rad(1.2),
              sun_intensity=0.6)
    return sky


def _rot_sol():
    # Azimute do jogo → direção no Blender; o Nishita mede a rotação a partir de +y.
    d = T(math.sin(rad(SUN_AZ)), 0, math.cos(rad(SUN_AZ)))
    return math.atan2(d.y, d.x) - math.pi / 2


def _neblina(nt, bsdf, densidade=0.00045, peso=1.0):
    """Perspectiva aérea como no jogo: mistura com a cor do céu na direção do olhar."""
    geo = _no(nt, 'ShaderNodeNewGeometry')
    neg = _no(nt, 'ShaderNodeVectorMath', operation='SCALE')
    neg.inputs['Scale'].default_value = -1
    nt.links.new(geo.outputs['Incoming'], neg.inputs[0])
    sep = _no(nt, 'ShaderNodeSeparateXYZ')
    nt.links.new(neg.outputs[0], sep.inputs[0])
    mz = _no(nt, 'ShaderNodeMath', operation='MAXIMUM')
    mz.inputs[1].default_value = 0.03
    nt.links.new(sep.outputs[2], mz.inputs[0])
    comb = _no(nt, 'ShaderNodeCombineXYZ')
    nt.links.new(sep.outputs[0], comb.inputs[0])
    nt.links.new(sep.outputs[1], comb.inputs[1])
    nt.links.new(mz.outputs[0], comb.inputs[2])
    sky = _ceu(nt, disco=False)
    nt.links.new(comb.outputs[0], sky.inputs['Vector'])
    emi = _no(nt, 'ShaderNodeEmission')
    emi.inputs['Strength'].default_value = CEU
    nt.links.new(sky.outputs[0], emi.inputs['Color'])
    cam = _no(nt, 'ShaderNodeCameraData')
    f1 = _no(nt, 'ShaderNodeMath', operation='MULTIPLY')
    f1.inputs[1].default_value = densidade
    nt.links.new(cam.outputs['View Distance'], f1.inputs[0])
    f2 = _no(nt, 'ShaderNodeMath', operation='POWER')
    f2.inputs[1].default_value = 2.0
    nt.links.new(f1.outputs[0], f2.inputs[0])
    f3 = _no(nt, 'ShaderNodeMath', operation='EXPONENT')
    neg2 = _no(nt, 'ShaderNodeMath', operation='MULTIPLY')
    neg2.inputs[1].default_value = -1
    nt.links.new(f2.outputs[0], neg2.inputs[0])
    nt.links.new(neg2.outputs[0], f3.inputs[0])
    fac = _no(nt, 'ShaderNodeMath', operation='MULTIPLY_ADD')
    fac.inputs[1].default_value = -peso
    fac.inputs[2].default_value = peso
    nt.links.new(f3.outputs[0], fac.inputs[0])
    # Só para o olhar (câmera e reflexos): se a névoa emitisse para os raios difusos,
    # iluminaria o próprio relevo e lavaria a cena inteira.
    lp = _no(nt, 'ShaderNodeLightPath')
    olhar = _no(nt, 'ShaderNodeMath', operation='MAXIMUM')
    nt.links.new(lp.outputs['Is Camera Ray'], olhar.inputs[0])
    nt.links.new(lp.outputs['Is Glossy Ray'], olhar.inputs[1])
    fac2 = _no(nt, 'ShaderNodeMath', operation='MULTIPLY')
    nt.links.new(fac.outputs[0], fac2.inputs[0])
    nt.links.new(olhar.outputs[0], fac2.inputs[1])
    mix = _no(nt, 'ShaderNodeMixShader')
    nt.links.new(fac2.outputs[0], mix.inputs[0])
    nt.links.new(bsdf.outputs[0], mix.inputs[1])
    nt.links.new(emi.outputs[0], mix.inputs[2])
    return mix


def mat_relevo():
    """Rocha, musgo e neve por altura e inclinação, como o shader BIOME do jogo."""
    m = bpy.data.materials.new('relevo')
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = _no(nt, 'ShaderNodeOutputMaterial')
    bsdf = _no(nt, 'ShaderNodeBsdfPrincipled')
    geo = _no(nt, 'ShaderNodeNewGeometry')
    pos = _no(nt, 'ShaderNodeSeparateXYZ')
    nor = _no(nt, 'ShaderNodeSeparateXYZ')
    nt.links.new(geo.outputs['Position'], pos.inputs[0])
    nt.links.new(geo.outputs['Normal'], nor.inputs[0])
    ru1 = _no(nt, 'ShaderNodeTexNoise')
    ru1.inputs['Scale'].default_value = 0.01
    ru1.inputs['Detail'].default_value = 8
    ru2 = _no(nt, 'ShaderNodeTexNoise')
    ru2.inputs['Scale'].default_value = 0.12
    ru2.inputs['Detail'].default_value = 6
    nt.links.new(geo.outputs['Position'], ru1.inputs['Vector'])
    nt.links.new(geo.outputs['Position'], ru2.inputs['Vector'])
    # Mesmas cores do shader BIOME do jogo: rocha clara/escura em manchas grandes, modulada por manchas finas.
    rocha0 = _no(nt, 'ShaderNodeValToRGB')
    rocha0.color_ramp.elements[0].color = (0.075, 0.07, 0.066, 1)
    rocha0.color_ramp.elements[1].color = (0.2, 0.185, 0.165, 1)
    rocha0.color_ramp.elements[0].position = 0.35
    rocha0.color_ramp.elements[1].position = 0.65
    rocha0.color_ramp.interpolation = 'EASE'
    nt.links.new(ru1.outputs['Fac'], rocha0.inputs[0])
    fino = _no(nt, 'ShaderNodeMapRange')
    fino.inputs['From Min'].default_value = 0.3
    fino.inputs['From Max'].default_value = 0.7
    fino.inputs['To Min'].default_value = 0.55
    fino.inputs['To Max'].default_value = 1.45
    nt.links.new(ru2.outputs['Fac'], fino.inputs[0])
    rocha = _no(nt, 'ShaderNodeVectorMath', operation='SCALE')
    nt.links.new(rocha0.outputs['Color'], rocha.inputs[0])
    nt.links.new(fino.outputs[0], rocha.inputs['Scale'])

    def faixa(entrada, a, b, extra=None):
        mr = _no(nt, 'ShaderNodeMapRange', interpolation_type='SMOOTHSTEP')
        mr.inputs['From Min'].default_value = a
        mr.inputs['From Max'].default_value = b
        if extra is not None:
            s = _no(nt, 'ShaderNodeMath', operation='MULTIPLY_ADD')
            s.inputs[1].default_value = extra[1]
            s.inputs[2].default_value = 0
            nt.links.new(extra[0], s.inputs[0])
            ad = _no(nt, 'ShaderNodeMath', operation='ADD')
            nt.links.new(entrada, ad.inputs[0])
            nt.links.new(s.outputs[0], ad.inputs[1])
            entrada = ad.outputs[0]
        nt.links.new(entrada, mr.inputs[0])
        return mr.outputs[0]

    def mult(a, b):
        n = _no(nt, 'ShaderNodeMath', operation='MULTIPLY')
        nt.links.new(a, n.inputs[0])
        nt.links.new(b, n.inputs[1])
        return n.outputs[0]

    def inv(a):
        n = _no(nt, 'ShaderNodeMath', operation='SUBTRACT')
        n.inputs[0].default_value = 1
        nt.links.new(a, n.inputs[1])
        return n.outputs[0]

    capim = mult(mult(faixa(nor.outputs[2], 0.66, 0.82, (ru2.outputs['Fac'], 0.3)),
                      inv(faixa(pos.outputs[2], 150, 260))), faixa(pos.outputs[2], 3, 9))
    neve = mult(faixa(nor.outputs[2], 0.45, 0.68, (ru1.outputs['Fac'], 0.3)), faixa(pos.outputs[2], 240, 340))

    def mistura(fac, a, b):
        n = _no(nt, 'ShaderNodeMix', data_type='RGBA')
        nt.links.new(fac, n.inputs['Factor'])
        ins = [s for s in n.inputs if s.enabled]
        for s, v in ((ins[1], a), (ins[2], b)):
            if isinstance(v, tuple):
                s.default_value = v
            else:
                nt.links.new(v, s)
        return [s for s in n.outputs if s.enabled][0]

    cor = mistura(capim, rocha.outputs[0], (0.035, 0.06, 0.016, 1))
    cor = mistura(neve, cor, (0.8, 0.83, 0.9, 1))
    nt.links.new(cor, bsdf.inputs['Base Color'])
    bsdf.inputs['Roughness'].default_value = 0.85
    # Relevo fino: estratos inclinados (ondas) somados a rachaduras (ruído rugoso).
    onda = _no(nt, 'ShaderNodeTexWave', wave_type='BANDS', bands_direction='Z')
    onda.inputs['Scale'].default_value = 0.02
    onda.inputs['Distortion'].default_value = 6
    onda.inputs['Detail'].default_value = 4
    nt.links.new(geo.outputs['Position'], onda.inputs['Vector'])
    ru3 = _no(nt, 'ShaderNodeTexNoise')
    ru3.inputs['Scale'].default_value = 0.35
    ru3.inputs['Detail'].default_value = 12
    ru3.inputs['Roughness'].default_value = 0.7
    nt.links.new(geo.outputs['Position'], ru3.inputs['Vector'])
    soma = _no(nt, 'ShaderNodeMath', operation='MULTIPLY_ADD')
    soma.inputs[1].default_value = 0.4
    nt.links.new(onda.outputs['Fac'], soma.inputs[0])
    nt.links.new(ru3.outputs['Fac'], soma.inputs[2])
    bump = _no(nt, 'ShaderNodeBump')
    bump.inputs['Strength'].default_value = 1.0
    bump.inputs['Distance'].default_value = 4.0
    nt.links.new(soma.outputs[0], bump.inputs['Height'])
    nt.links.new(bump.outputs[0], bsdf.inputs['Normal'])
    nt.links.new(_neblina(nt, bsdf).outputs[0], out.inputs[0])
    return m


def mat_agua():
    m = bpy.data.materials.new('agua')
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = _no(nt, 'ShaderNodeOutputMaterial')
    bsdf = _no(nt, 'ShaderNodeBsdfPrincipled')
    bsdf.inputs['Base Color'].default_value = (0.004, 0.018, 0.022, 1)
    bsdf.inputs['Roughness'].default_value = 0.035
    bsdf.inputs['IOR'].default_value = 1.33
    tc = _no(nt, 'ShaderNodeTexCoord')
    mp = _no(nt, 'ShaderNodeMapping')
    mp.inputs['Scale'].default_value = (1.0, 0.35, 1.0)  # ondulação alongada ao longo do fiorde
    nt.links.new(tc.outputs['Object'], mp.inputs['Vector'])
    r1 = _no(nt, 'ShaderNodeTexNoise')
    r1.inputs['Scale'].default_value = 0.5
    r1.inputs['Detail'].default_value = 8
    r1.inputs['Roughness'].default_value = 0.6
    nt.links.new(mp.outputs[0], r1.inputs['Vector'])
    bump = _no(nt, 'ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.12
    bump.inputs['Distance'].default_value = 0.3
    nt.links.new(r1.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs[0], bsdf.inputs['Normal'])
    nt.links.new(_neblina(nt, bsdf, peso=0.6).outputs[0], out.inputs[0])
    return m


def mat_facho():
    """Facho do farol: emissão que some nas bordas do cone, sobre transparência."""
    m = bpy.data.materials.new('facho')
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = _no(nt, 'ShaderNodeOutputMaterial')
    lw = _no(nt, 'ShaderNodeLayerWeight')
    lw.inputs['Blend'].default_value = 0.5
    inv = _no(nt, 'ShaderNodeMath', operation='SUBTRACT')
    inv.inputs[0].default_value = 1
    nt.links.new(lw.outputs['Facing'], inv.inputs[1])
    pw = _no(nt, 'ShaderNodeMath', operation='POWER')
    pw.inputs[1].default_value = 2.0
    nt.links.new(inv.outputs[0], pw.inputs[0])
    tc = _no(nt, 'ShaderNodeTexCoord')
    sep = _no(nt, 'ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Generated'], sep.inputs[0])
    ao_longo = _no(nt, 'ShaderNodeMath', operation='POWER')
    ao_longo.inputs[1].default_value = 3.0
    nt.links.new(sep.outputs[2], ao_longo.inputs[0])
    k = _no(nt, 'ShaderNodeMath', operation='MULTIPLY')
    nt.links.new(pw.outputs[0], k.inputs[0])
    nt.links.new(ao_longo.outputs[0], k.inputs[1])
    forca = _no(nt, 'ShaderNodeMath', operation='MULTIPLY')
    forca.inputs[1].default_value = 0.4
    nt.links.new(k.outputs[0], forca.inputs[0])
    emi = _no(nt, 'ShaderNodeEmission')
    emi.inputs['Color'].default_value = (1.0, 0.8, 0.55, 1)
    nt.links.new(forca.outputs[0], emi.inputs['Strength'])
    tr = _no(nt, 'ShaderNodeBsdfTransparent')
    add = _no(nt, 'ShaderNodeAddShader')
    nt.links.new(emi.outputs[0], add.inputs[0])
    nt.links.new(tr.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs[0])
    return m


# ============================================================ planador (porte do three.js)
def aerofolio(n, t):
    up = []
    for i in range(n + 1):
        x = (1 + math.cos(i / n * math.pi)) / 2
        yt = 5 * t * (0.2969 * math.sqrt(x) - 0.126 * x - 0.3516 * x * x + 0.2843 * x ** 3 - 0.1036 * x ** 4)
        yc = 0.025 * math.sin(math.pi * x)
        up.append((x, yc + yt, yc))
    anel = [(x, y) for x, y, _ in up]
    for i in range(n - 1, 0, -1):
        x, _, yc = up[i]
        anel.append((x, 2 * yc - anel[i][1]))
    return anel


def planador():
    tinta = simples('tinta', (0.85, 0.84, 0.8), rug=0.25)
    tinta.node_tree.nodes['Principled BSDF'].inputs['Coat Weight'].default_value = 1.0
    friso = simples('friso', (0.55, 0.02, 0.03), rug=0.3)
    friso.node_tree.nodes['Principled BSDF'].inputs['Coat Weight'].default_value = 1.0
    vidro = simples('canopi', (0.01, 0.015, 0.02), rug=0.02)
    escuro = simples('escuro', (0.02, 0.02, 0.02), rug=0.6)
    m = Malha('Planador')
    # Fuselagem: perfil de revolução em torno do eixo z do jogo, bico em -z.
    perfil = [(0.005, 0.02), (0.18, 0.12), (0.31, 0.4), (0.4, 0.85), (0.44, 1.4), (0.42, 2.0), (0.34, 2.8),
              (0.22, 3.7), (0.15, 4.8), (0.12, 6.0), (0.09, 6.6), (0.005, 6.78)]
    secoes = []
    for r, y in perfil:
        secoes.append([T(r * math.sin(f), -1.08 * r * math.cos(f), y - 2.4)
                       for f in np.linspace(0, math.tau, 32, endpoint=False)])
    m.loft(secoes, tinta)

    def loft_asa(estacoes, anel, mat):
        m.loft([[T(s['x'], s['y'] + py * s['c'], s['z'] + px * s['c']) for px, py in anel] for s in estacoes], mat)

    asa, cauda = aerofolio(16, 0.14), aerofolio(12, 0.1)
    est = lambda xs: [{'x': x, 'y': 0.22 + abs(x) * 0.055, 'z': z, 'c': c} for x, c, z in xs]
    branco = [(0, 1.0, -1.15), (2.3, 0.93, -1.12), (4.6, 0.68, -1.02), (5.35, 0.56, -0.97)]
    vermelho = [(5.35, 0.56, -0.97), (6.0, 0.4, -0.9)]
    for sg in (1, -1):
        loft_asa(est([(x * sg, c, z) for x, c, z in branco]), asa, tinta)
        loft_asa(est([(x * sg, c, z) for x, c, z in vermelho]), asa, friso)
        loft_asa([{'x': 0, 'y': 1.43, 'z': 3.95, 'c': 0.55}, {'x': 1.55 * sg, 'y': 1.43, 'z': 4.1, 'c': 0.36}], cauda, friso)
    # Deriva: mesmo loft do jogo girado 90° em z (x, y) → (-y, x), subida de 0,1.
    m.loft([[T(-(py * s['c']), s['x'] + 0.1, s['z'] + px * s['c']) for px, py in cauda]
            for s in ({'x': 0, 'z': 3.55, 'c': 0.95}, {'x': 1.35, 'z': 3.95, 'c': 0.55})], tinta)
    m.esfera(T(0, 0.26, -1.25), 1.0, vidro, seg=24, escala=(0.35, 1.05, 0.3))
    m.esfera(T(0, 0.34, -1.05), 0.13, escuro)
    m.cilindro(T(0, 0, -2.4), T(0, 0, -2.66), 0.14, 0.0, escuro, seg=16)
    luzes = [((-6.02, 0.55, -0.72), (1, 0.03, 0.02)), ((6.02, 0.55, -0.72), (0.03, 1, 0.1)), ((0, 1.47, 4.3), (1, 1, 1))]
    for p, c in luzes:
        m.esfera(T(*p), 0.09, simples('nav', c, emissao=c, forca=40), seg=8)
    return m.objeto()


# ============================================================ cena
def renderizar(M, farol, vila, igreja, saida, rapido=False):
    cena = bpy.context.scene
    criados = []
    antes = {o: (o.location.copy(), o.rotation_euler.copy(), o.scale.copy()) for o in (farol, vila, igreja)}

    def por(ob, z, lado, d, escala, alt=0.0, extra=0.0):
        x = lado * (float(shore_at(z, lado)) + d)
        slope = (float(shore_at(z + 20, lado)) - float(shore_at(z - 20, lado))) / 40
        ob.location = T(x, alt, z)
        # Mesma orientação do jogo (rotação em y no three.js = rotação em z no Blender).
        ob.rotation_euler = (0, 0, math.atan2(-lado, slope) + extra)
        ob.scale = (escala,) * 3
        return x

    por(farol, -230, 1, -16, 1.5)
    por(vila, -360, -1, -5, 1.3)
    xi = por(igreja, -520, -1, 18, 1.5, alt=13, extra=math.pi / 2)

    rel = relevo([(xi, -520, 13)])
    rel.data.materials.append(mat_relevo())
    rel.visible_shadow = False  # como no jogo: com o sol baixo, os paredões deixariam o fiorde todo na sombra
    criados.append(rel)
    bpy.ops.mesh.primitive_plane_add(size=12000, location=(0, 3000, 0))
    agua = bpy.context.active_object
    agua.data.materials.append(mat_agua())
    criados.append(agua)

    # Planador inclinado numa curva suave, rente à água.
    pl = planador()
    pl.location = T(1, 18, 0)
    pl.rotation_euler = (rad(4), rad(22), rad(8))
    criados.append(pl)

    # Facho do farol: dois cones a partir da lâmpada.
    lamp = farol.matrix_world @ Vector((0, 0, 19.35))
    for ang in (rad(28), rad(208)):
        bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=16, radius2=0.5, depth=240, end_fill_type='NOTHING')
        c = bpy.context.active_object
        c.data.materials.append(mat_facho())
        d = Vector((math.cos(ang), math.sin(ang), -0.02)).normalized()
        c.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        c.location = lamp + d * 120
        criados.append(c)
    M.lampada.node_tree.nodes['Principled BSDF'].inputs['Emission Strength'].default_value = 400
    M.lanterna.node_tree.nodes['Principled BSDF'].inputs['Emission Color'].default_value = (1, 0.8, 0.55, 1)
    M.lanterna.node_tree.nodes['Principled BSDF'].inputs['Emission Strength'].default_value = 3
    M.luz.node_tree.nodes['Principled BSDF'].inputs['Emission Strength'].default_value = 6

    # Céu físico: o disco do sol só aparece para a câmera; a luz direta vem de uma lâmpada Sun.
    w = cena.world
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputWorld')
    bg = nt.nodes.new('ShaderNodeBackground')
    bg.inputs['Strength'].default_value = CEU
    sem = _ceu(nt, disco=False)
    com = _ceu(nt, disco=True)
    lp = nt.nodes.new('ShaderNodeLightPath')
    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    ins = [s for s in mix.inputs if s.enabled]
    nt.links.new(lp.outputs['Is Camera Ray'], ins[0])
    nt.links.new(sem.outputs[0], ins[1])
    nt.links.new(com.outputs[0], ins[2])
    nt.links.new([s for s in mix.outputs if s.enabled][0], bg.inputs['Color'])
    nt.links.new(bg.outputs[0], out.inputs[0])
    sol = bpy.data.lights.new('Sol', 'SUN')
    sol.energy = 7.0
    sol.color = (1.0, 0.62, 0.36)
    sol.angle = rad(0.8)
    sol_ob = bpy.data.objects.new('Sol', sol)
    sol_ob.visible_glossy = False  # o sol está atrás do paredão; sem o relevo fazendo sombra, brilharia na água
    cena.collection.objects.link(sol_ob)
    dir_sol = T(math.sin(rad(SUN_AZ)) * math.cos(rad(SUN_ELEV)), math.sin(rad(SUN_ELEV)),
                math.cos(rad(SUN_AZ)) * math.cos(rad(SUN_ELEV)))
    sol_ob.rotation_euler = dir_sol.to_track_quat('Z', 'Y').to_euler()
    criados.append(sol_ob)

    cam_d = bpy.data.cameras.new('Camera')
    cam_d.lens = 42
    cam = bpy.data.objects.new('Camera', cam_d)
    cena.collection.objects.link(cam)
    cam.location = T(7, 24, 40)
    alvo = T(-4, 0, -300)
    cam.rotation_euler = (alvo - cam.location).to_track_quat('-Z', 'Y').to_euler()
    cena.camera = cam
    criados.append(cam)

    r = cena.render
    r.engine = 'CYCLES'
    cena.cycles.device = 'CPU'
    cena.cycles.samples = 24 if rapido else 256
    cena.cycles.use_denoising = True
    cena.cycles.denoiser = 'OPENIMAGEDENOISE'
    cena.cycles.max_bounces = 6
    r.resolution_x, r.resolution_y = 1600, 840
    r.resolution_percentage = 50 if rapido else 100
    cena.view_settings.view_transform = 'AgX'
    cena.view_settings.look = 'AgX - Medium High Contrast'
    cena.view_settings.exposure = 0.2
    r.image_settings.file_format = 'JPEG'
    r.image_settings.quality = 88
    r.filepath = saida
    # Brilho em volta das luzes e do céu, como o bloom do jogo.
    cena.use_nodes = True
    ct = cena.node_tree
    ct.nodes.clear()
    rl = ct.nodes.new('CompositorNodeRLayers')
    gl = ct.nodes.new('CompositorNodeGlare')
    gl.glare_type = 'FOG_GLOW'
    gl.quality = 'HIGH'
    gl.inputs['Threshold'].default_value = 1.0
    gl.inputs['Strength'].default_value = 0.35
    gl.inputs['Size'].default_value = 0.4
    co = ct.nodes.new('CompositorNodeComposite')
    ct.links.new(rl.outputs['Image'], gl.inputs['Image'])
    ct.links.new(gl.outputs['Image'], co.inputs['Image'])
    bpy.ops.render.render(write_still=True)
    cena.use_nodes = False
    print('Cartaz:', saida)

    # Desfaz tudo para o cozimento das texturas não enxergar o cenário do cartaz.
    for ob in criados:
        bpy.data.objects.remove(ob, do_unlink=True)
    for o, (loc, rot, esc) in antes.items():
        o.location, o.rotation_euler, o.scale = loc, rot, esc
    M.luz.node_tree.nodes['Principled BSDF'].inputs['Emission Strength'].default_value = 1.0
    bpy.context.view_layer.update()
