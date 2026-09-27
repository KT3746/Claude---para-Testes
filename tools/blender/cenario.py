"""Constrói no Blender os marcos do fiorde e exporta para o jogo.

Três construções típicas da costa norueguesa, modeladas por código:
  - Farol: torre de ferro vermelha numa ilhota, com a casa do faroleiro.
  - Vila: rorbuer (cabanas de pescador sobre palafitas), cais e barcos.
  - Igreja: stavkirke de madeira alcatroada, telhados em camadas e dragões.

Os materiais são procedurais (tábuas, telhas de madeira, líquen...). Para o
jogo, o Cycles "cozinha" cor, oclusão de ambiente e janelas acesas numa
textura por construção, e tudo sai num único assets/cenario.glb.

Uso (Blender como módulo Python, `pip install bpy==4.5.*`, ou o Blender 4.2+):
    python3 tools/blender/cenario.py            # gera assets/cenario.glb
    python3 tools/blender/cenario.py --cartaz   # também renderiza assets/cartaz.jpg
    blender -b -P tools/blender/cenario.py -- --cartaz
"""
import math
import os
import random
import sys

import bpy  # antes do bmesh: é o bpy que registra os módulos do Blender
import bmesh
import numpy as np
from mathutils import Matrix, Vector, noise

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.normpath(os.path.join(AQUI, '..', '..'))
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
RAPIDO = '--rapido' in ARGS  # texturas e amostras menores, para testar

rad = math.radians


# ============================================================ materiais
def _no(nt, tipo, x, y, **props):
    n = nt.nodes.new(tipo)
    n.location = (x, y)
    for k, v in props.items():
        setattr(n, k, v)
    return n


def _s(soquetes, nome):
    """Soquete ativo pelo nome (o Mix tem vários "A", "B" e "Result", um por tipo)."""
    return next(x for x in soquetes if x.name == nome and x.enabled)


def _coords_planas(nt):
    """(h, z): h corre na horizontal de cada face (y nas faces voltadas para ±x, senão x).

    Serve para tábuas, telhas e pranchas em paredes e telhados alinhados aos eixos,
    sem depender de UV.
    """
    tc = _no(nt, 'ShaderNodeTexCoord', -1400, 0)
    geo = _no(nt, 'ShaderNodeNewGeometry', -1400, -300)
    pos = _no(nt, 'ShaderNodeSeparateXYZ', -1200, 0)
    nor = _no(nt, 'ShaderNodeSeparateXYZ', -1200, -300)
    nt.links.new(tc.outputs['Object'], pos.inputs[0])
    nt.links.new(geo.outputs['Normal'], nor.inputs[0])
    ax = _no(nt, 'ShaderNodeMath', -1000, -250, operation='ABSOLUTE')
    ay = _no(nt, 'ShaderNodeMath', -1000, -400, operation='ABSOLUTE')
    nt.links.new(nor.outputs[0], ax.inputs[0])
    nt.links.new(nor.outputs[1], ay.inputs[0])
    lado = _no(nt, 'ShaderNodeMath', -850, -300, operation='GREATER_THAN')
    nt.links.new(ax.outputs[0], lado.inputs[0])
    nt.links.new(ay.outputs[0], lado.inputs[1])
    h = _no(nt, 'ShaderNodeMix', -700, 0, data_type='FLOAT')
    nt.links.new(lado.outputs[0], h.inputs['Factor'])
    nt.links.new(pos.outputs[0], _s(h.inputs, 'A'))
    nt.links.new(pos.outputs[1], _s(h.inputs, 'B'))
    vec = _no(nt, 'ShaderNodeCombineXYZ', -550, 0)
    nt.links.new(_s(h.outputs, 'Result'), vec.inputs[0])
    nt.links.new(pos.outputs[2], vec.inputs[1])
    return vec.outputs[0], tc.outputs['Object']


def material(nome, cor, cor2=None, junta=None, largura=0.3, altura=50.0, junta_tam=0.012,
             desloc=0.5, rug=0.8, sujeira=0.25, luz=None, metal=0.0, escala_ruido=2.5, riscos=False):
    """Material procedural com tábuas/telhas (Brick Texture) e ruído de sujeira."""
    m = bpy.data.materials.new(nome)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = _no(nt, 'ShaderNodeOutputMaterial', 600, 0)
    bsdf = _no(nt, 'ShaderNodeBsdfPrincipled', 300, 0)
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    bsdf.inputs['Roughness'].default_value = rug
    bsdf.inputs['Metallic'].default_value = metal
    uv, obj = _coords_planas(nt)
    if junta is not None:
        tij = _no(nt, 'ShaderNodeTexBrick', -300, 0, offset=desloc)
        nt.links.new(uv, tij.inputs['Vector'])
        tij.inputs['Color1'].default_value = (*cor, 1)
        tij.inputs['Color2'].default_value = (*(cor2 or cor), 1)
        tij.inputs['Mortar'].default_value = (*junta, 1)
        tij.inputs['Scale'].default_value = 1.0
        tij.inputs['Mortar Size'].default_value = junta_tam
        tij.inputs['Mortar Smooth'].default_value = 0.3
        tij.inputs['Brick Width'].default_value = largura
        tij.inputs['Row Height'].default_value = altura
        base = tij.outputs['Color']
    else:
        rgb = _no(nt, 'ShaderNodeRGB', -300, 0)
        rgb.outputs[0].default_value = (*cor, 1)
        base = rgb.outputs[0]
    # Sujeira: ruído que escurece e desbota em manchas; "riscos" estica o ruído na vertical (ferrugem).
    vec = obj
    if riscos:
        mp = _no(nt, 'ShaderNodeMapping', -500, -350)
        mp.inputs['Scale'].default_value = (1.0, 1.0, 0.08)
        nt.links.new(obj, mp.inputs['Vector'])
        vec = mp.outputs[0]
    ru = _no(nt, 'ShaderNodeTexNoise', -300, -350)
    ru.inputs['Scale'].default_value = escala_ruido
    ru.inputs['Detail'].default_value = 6
    nt.links.new(vec, ru.inputs['Vector'])
    rampa = _no(nt, 'ShaderNodeMapRange', -100, -350)
    rampa.inputs['From Min'].default_value = 0.3
    rampa.inputs['From Max'].default_value = 0.7
    rampa.inputs['To Min'].default_value = 1.0 - sujeira
    rampa.inputs['To Max'].default_value = 1.0 + sujeira * 0.4
    nt.links.new(ru.outputs['Fac'], rampa.inputs[0])
    mult = _no(nt, 'ShaderNodeMix', 100, 0, data_type='RGBA', blend_type='MULTIPLY')
    mult.inputs['Factor'].default_value = 1.0
    nt.links.new(base, _s(mult.inputs, 'A'))
    nt.links.new(rampa.outputs[0], _s(mult.inputs, 'B'))
    nt.links.new(_s(mult.outputs, 'Result'), bsdf.inputs['Base Color'])
    if luz:
        bsdf.inputs['Emission Color'].default_value = (*luz, 1)
        bsdf.inputs['Emission Strength'].default_value = 1.0
    return m


def material_rocha(nome='rocha'):
    """Rocha escura com veios e manchas de líquen laranja (Xanthoria)."""
    m = bpy.data.materials.new(nome)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = _no(nt, 'ShaderNodeOutputMaterial', 800, 0)
    bsdf = _no(nt, 'ShaderNodeBsdfPrincipled', 500, 0)
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    bsdf.inputs['Roughness'].default_value = 0.9
    tc = _no(nt, 'ShaderNodeTexCoord', -900, 0)
    ru = _no(nt, 'ShaderNodeTexNoise', -600, 100)
    ru.inputs['Scale'].default_value = 0.35
    ru.inputs['Detail'].default_value = 10
    ru.inputs['Roughness'].default_value = 0.62
    nt.links.new(tc.outputs['Object'], ru.inputs['Vector'])
    cr = _no(nt, 'ShaderNodeValToRGB', -350, 100)
    cr.color_ramp.elements[0].position = 0.35
    cr.color_ramp.elements[0].color = (0.035, 0.034, 0.032, 1)
    cr.color_ramp.elements[1].position = 0.7
    cr.color_ramp.elements[1].color = (0.16, 0.15, 0.135, 1)
    nt.links.new(ru.outputs['Fac'], cr.inputs[0])
    vo = _no(nt, 'ShaderNodeTexVoronoi', -600, -250)
    vo.inputs['Scale'].default_value = 1.6
    vo.inputs['Randomness'].default_value = 1.0
    nt.links.new(tc.outputs['Object'], vo.inputs['Vector'])
    li = _no(nt, 'ShaderNodeMapRange', -350, -250)
    li.inputs['From Min'].default_value = 0.22
    li.inputs['From Max'].default_value = 0.12
    nt.links.new(vo.outputs['Distance'], li.inputs[0])
    mix = _no(nt, 'ShaderNodeMix', 200, 0, data_type='RGBA')
    _s(mix.inputs, 'B').default_value = (0.42, 0.16, 0.02, 1)
    nt.links.new(li.outputs[0], mix.inputs['Factor'])
    nt.links.new(cr.outputs['Color'], _s(mix.inputs, 'A'))
    nt.links.new(_s(mix.outputs, 'Result'), bsdf.inputs['Base Color'])
    bump = _no(nt, 'ShaderNodeBump', 200, -300)
    bump.inputs['Strength'].default_value = 0.6
    nt.links.new(ru.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs[0], bsdf.inputs['Normal'])
    return m


def simples(nome, cor, rug=0.5, metal=0.0, emissao=None, forca=0.0, alfa=1.0, transm=0.0):
    m = bpy.data.materials.new(nome)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*cor, 1)
    b.inputs['Roughness'].default_value = rug
    b.inputs['Metallic'].default_value = metal
    b.inputs['Alpha'].default_value = alfa
    b.inputs['Transmission Weight'].default_value = transm
    if emissao:
        b.inputs['Emission Color'].default_value = (*emissao, 1)
        b.inputs['Emission Strength'].default_value = forca
    return m


class Mat:
    pass


def criar_materiais():
    M = Mat()
    # Tábuas verticais (largura 0,3 m, sem juntas horizontais).
    M.falu = material('falu', (0.26, 0.032, 0.022), (0.31, 0.042, 0.028), (0.07, 0.012, 0.008))
    M.ocre = material('ocre', (0.46, 0.26, 0.05), (0.52, 0.3, 0.065), (0.14, 0.07, 0.015))
    M.branco = material('branco', (0.62, 0.62, 0.59), (0.68, 0.68, 0.65), (0.3, 0.3, 0.28), sujeira=0.18)
    M.alcatrao = material('alcatrao', (0.03, 0.019, 0.012), (0.042, 0.027, 0.017), (0.012, 0.008, 0.005),
                          largura=0.24, rug=0.55)
    # Telhas de madeira escalonadas e telhas de barro.
    M.telhas_igreja = material('telhas_igreja', (0.038, 0.026, 0.018), (0.058, 0.04, 0.027), (0.01, 0.007, 0.005),
                               largura=0.2, altura=0.28, junta_tam=0.02, rug=0.7)
    M.telha = material('telha', (0.035, 0.035, 0.04), (0.05, 0.046, 0.046), (0.012, 0.012, 0.014),
                       largura=0.32, altura=0.36, junta_tam=0.025, rug=0.6)
    M.telha_verm = material('telha_verm', (0.22, 0.035, 0.02), (0.27, 0.05, 0.028), (0.06, 0.012, 0.008),
                            largura=0.3, altura=0.34, junta_tam=0.025, rug=0.6)
    M.turfa = material('turfa', (0.028, 0.05, 0.012), (0.055, 0.07, 0.018), (0.07, 0.055, 0.022),
                       largura=0.9, altura=0.7, junta_tam=0.15, desloc=0.37, sujeira=0.5, escala_ruido=1.2)
    M.cais = material('cais', (0.17, 0.155, 0.13), (0.22, 0.2, 0.165), (0.03, 0.025, 0.02),
                      largura=0.26, altura=5.0, junta_tam=0.02, sujeira=0.35)
    M.estaca = material('estaca', (0.045, 0.035, 0.026), sujeira=0.3)
    M.moldura = material('moldura', (0.72, 0.72, 0.69), sujeira=0.1)
    M.porta = material('porta', (0.02, 0.07, 0.06), (0.025, 0.08, 0.07), (0.005, 0.02, 0.018), largura=0.12)
    M.ferro = material('ferro', (0.38, 0.028, 0.018), sujeira=0.3, rug=0.45, escala_ruido=1.5, riscos=True)
    M.concreto = material('concreto', (0.55, 0.54, 0.51), sujeira=0.3, escala_ruido=1.2)
    M.metal = material('metal', (0.02, 0.02, 0.022), rug=0.4, metal=0.6, sujeira=0.1)
    M.vidro = material('vidro', (0.008, 0.01, 0.013), rug=0.08, sujeira=0.0)
    M.luz = material('luz', (0.02, 0.015, 0.01), rug=0.1, sujeira=0.0, luz=(1.0, 0.55, 0.22))
    M.rocha = material_rocha()
    # Fora do cozimento: vidro da lanterna e lâmpada do farol ganham material próprio no jogo.
    M.lanterna = simples('Farol_Vidro', (0.7, 0.8, 0.85), rug=0.05, alfa=0.35, transm=1.0)
    M.lampada = simples('Farol_Lampada', (1, 0.9, 0.7), emissao=(1.0, 0.85, 0.6), forca=30)
    return M


# ============================================================ geometria
def _base(z_para):
    """Matriz de rotação que leva +z para a direção dada."""
    return z_para.normalized().to_track_quat('Z', 'Y').to_matrix().to_4x4()


class Malha:
    """Acumula primitivas num bmesh, com índice de material por face."""

    def __init__(self, nome):
        self.nome = nome
        self.bm = bmesh.new()
        self.mats = []

    def _marca(self, n0, mat, liso=None):
        if mat not in self.mats:
            self.mats.append(mat)
        i = self.mats.index(mat)
        self.bm.faces.ensure_lookup_table()
        for f in self.bm.faces[n0:]:
            f.material_index = i
            if liso is not None:
                f.smooth = abs(f.normal.dot(liso)) < 0.95
        return self

    def caixa(self, c, s, mat, rz=0.0, ry=0.0, rx=0.0):
        n0 = len(self.bm.faces)
        R = (Matrix.Rotation(rz, 4, 'Z') @ Matrix.Rotation(ry, 4, 'Y') @ Matrix.Rotation(rx, 4, 'X'))
        M = Matrix.Translation(c) @ R @ Matrix.Diagonal((*s, 1))
        bmesh.ops.create_cube(self.bm, size=1.0, matrix=M)
        self.bm.normal_update()
        return self._marca(n0, mat)

    def viga(self, p0, p1, larg, alt, mat):
        """Caixa de p0 a p1 com seção larg × alt (alt fica o mais vertical possível)."""
        p0, p1 = Vector(p0), Vector(p1)
        d = p1 - p0
        eixo = d.normalized()
        lado = eixo.cross(Vector((0, 0, 1)))
        if lado.length < 1e-4:
            lado = Vector((1, 0, 0))
        lado.normalize()
        cima = lado.cross(eixo)
        R = Matrix((eixo, lado, cima)).transposed().to_4x4()
        M = Matrix.Translation((p0 + p1) / 2) @ R @ Matrix.Diagonal((d.length, larg, alt, 1))
        n0 = len(self.bm.faces)
        bmesh.ops.create_cube(self.bm, size=1.0, matrix=M)
        self.bm.normal_update()
        return self._marca(n0, mat)

    def cilindro(self, p0, p1, r0, r1, mat, seg=12, tampa=True):
        p0, p1 = Vector(p0), Vector(p1)
        d = p1 - p0
        M = Matrix.Translation((p0 + p1) / 2) @ _base(d)
        n0 = len(self.bm.faces)
        bmesh.ops.create_cone(self.bm, cap_ends=tampa, cap_tris=False, segments=seg,
                              radius1=r0, radius2=r1, depth=d.length, matrix=M)
        self.bm.normal_update()
        return self._marca(n0, mat, liso=d.normalized())

    def esfera(self, c, r, mat, seg=12, escala=(1, 1, 1)):
        n0 = len(self.bm.faces)
        M = Matrix.Translation(c) @ Matrix.Diagonal((*escala, 1))
        bmesh.ops.create_uvsphere(self.bm, u_segments=seg, v_segments=max(4, seg // 2), radius=r, matrix=M)
        self.bm.normal_update()
        n1 = len(self.bm.faces)
        self._marca(n0, mat)
        self.bm.faces.ensure_lookup_table()
        for f in self.bm.faces[n0:n1]:
            f.smooth = True
        return self

    def prisma(self, pts, esp, c, mat, eixo='y'):
        """Polígono convexo no plano (u, z), extrudado ao longo de y (ou x) com espessura esp."""
        bm = self.bm
        c = Vector(c)
        def P(u, z, t):
            return c + (Vector((u, t, z)) if eixo == 'y' else Vector((t, u, z)))
        n0 = len(bm.faces)
        a = [bm.verts.new(P(u, z, -esp / 2)) for u, z in pts]
        b = [bm.verts.new(P(u, z, esp / 2)) for u, z in pts]
        bm.faces.new(a[::-1] if eixo == 'y' else a)
        bm.faces.new(b if eixo == 'y' else b[::-1])
        n = len(pts)
        for i in range(n):
            j = (i + 1) % n
            q = [a[i], a[j], b[j], b[i]]
            bm.faces.new(q if eixo == 'y' else q[::-1])
        bm.normal_update()
        return self._marca(n0, mat)

    def loft(self, secoes, mat, fechar=True):
        """Une anéis (listas de Vector com o mesmo número de pontos) em sequência."""
        bm = self.bm
        n0 = len(bm.faces)
        aneis = [[bm.verts.new(p) for p in s] for s in secoes]
        R = len(aneis[0])
        for s in range(len(aneis) - 1):
            for k in range(R):
                a, b = aneis[s][k], aneis[s][(k + 1) % R]
                c, d = aneis[s + 1][k], aneis[s + 1][(k + 1) % R]
                bm.faces.new((a, b, d, c))
        if fechar:
            bm.faces.new(aneis[0][::-1])
            bm.faces.new(aneis[-1])
        bm.normal_update()
        self._marca(n0, mat)
        bm.faces.ensure_lookup_table()
        for f in bm.faces[n0:]:
            f.smooth = len(f.verts) == 4
        return self

    def objeto(self, pai=None):
        me = bpy.data.meshes.new(self.nome)
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces)
        self.bm.to_mesh(me)
        self.bm.free()
        for m in self.mats:
            me.materials.append(m)
        ob = bpy.data.objects.new(self.nome, me)
        bpy.context.scene.collection.objects.link(ob)
        ob.parent = pai
        return ob


def vazio(nome):
    e = bpy.data.objects.new(nome, None)
    bpy.context.scene.collection.objects.link(e)
    return e


# ------------------------------------------------------------ peças
def janela(m, M, c, eixo, sinal, w=0.9, h=1.1, acesa=False, cruz=True):
    """Janela com moldura branca saliente; c no plano da parede, normal = sinal·eixo."""
    c = Vector(c)
    n = Vector((0, sinal, 0)) if eixo == 'y' else Vector((sinal, 0, 0))
    t = Vector((1, 0, 0)) if eixo == 'y' else Vector((0, 1, 0))
    def S(tt, nn, zz):
        return (tt, nn, zz) if eixo == 'y' else (nn, tt, zz)
    z = Vector((0, 0, 1))
    m.caixa(c + n * 0.02, S(w, 0.08, h), M.luz if acesa else M.vidro)
    for s in (-1, 1):
        m.caixa(c + n * 0.06 + z * s * (h / 2 + 0.05), S(w + 0.24, 0.12, 0.1), M.moldura)
        m.caixa(c + n * 0.06 + t * s * (w / 2 + 0.05), S(0.1, 0.12, h), M.moldura)
    if cruz:
        m.caixa(c + n * 0.05, S(0.05, 0.08, h), M.moldura)
        m.caixa(c + n * 0.05, S(w, 0.08, 0.05), M.moldura)


def casa(m, M, x0, y0, piso, larg, prof, alt, parede, telhado, inclin=38, palafitas=True,
         acesas=0.5, rng=random, chamine=True, porta_lado=-1):
    """Casa de empena com a fachada da porta voltada para porta_lado·y (-1: para a água)."""
    a = rad(inclin)
    hg = larg / 2 * math.tan(a)
    beiral = 0.45
    if palafitas:
        for ix in np.linspace(-larg / 2 + 0.25, larg / 2 - 0.25, 3):
            for iy in np.linspace(-prof / 2 + 0.25, prof / 2 - 0.25, 4):
                m.cilindro((x0 + ix, y0 + iy, -5), (x0 + ix, y0 + iy, piso - 0.3), 0.17, 0.17, M.estaca, seg=8)
        for iy in (-prof / 2 + 0.25, prof / 2 - 0.25):
            m.viga((x0 - larg / 2 + 0.25, y0 + iy, -0.5), (x0 + larg / 2 - 0.25, y0 + iy, piso - 0.6), 0.12, 0.2, M.estaca)
            m.viga((x0 + larg / 2 - 0.25, y0 + iy, -0.5), (x0 - larg / 2 + 0.25, y0 + iy, piso - 0.6), 0.12, 0.2, M.estaca)
    else:
        m.caixa((x0, y0, piso - 1.2), (larg + 0.2, prof + 0.2, 2.4), M.concreto)
    m.caixa((x0, y0, piso - 0.15), (larg + 0.3, prof + 0.3, 0.3), M.cais)
    m.caixa((x0, y0, piso + alt / 2), (larg, prof, alt), parede)
    for s in (-1, 1):
        m.prisma([(-larg / 2, 0), (larg / 2, 0), (0, hg)], 0.3, (x0, y0 + s * (prof / 2 - 0.15), piso + alt), parede)
    # Cantoneiras brancas.
    for sx in (-1, 1):
        for sy in (-1, 1):
            m.caixa((x0 + sx * larg / 2, y0 + sy * prof / 2, piso + alt / 2), (0.24, 0.24, alt), M.moldura)
    # Telhado: duas águas com beiral, cumeeira e testeiras brancas nas empenas.
    ws = (larg / 2 + beiral) / math.cos(a)
    topo = piso + alt + hg
    for s in (-1, 1):
        cx = x0 + s * (ws / 2 * math.cos(a) - 0.02)
        cz = topo - ws / 2 * math.sin(a) + 0.2
        m.caixa((cx, y0, cz), (ws, prof + 2 * beiral, 0.3), telhado, ry=s * a)
        for sy in (-1, 1):
            m.caixa((cx, y0 + sy * (prof / 2 + beiral + 0.03), cz - 0.06), (ws, 0.1, 0.46), M.moldura, ry=s * a)
    m.caixa((x0, y0, topo + 0.3), (0.35, prof + 2 * beiral, 0.25), telhado)
    if chamine:
        cxs = x0 + larg * 0.22
        m.caixa((cxs, y0 + prof * 0.2, topo - 0.1), (0.55, 0.55, 2.0), M.concreto)
        m.caixa((cxs, y0 + prof * 0.2, topo + 0.95), (0.7, 0.7, 0.12), M.metal)
    # Fachada da porta.
    yf = y0 + porta_lado * prof / 2
    m.caixa((x0, yf + porta_lado * 0.03, piso + 1.05), (1.0, 0.1, 2.1), M.porta)
    m.caixa((x0, yf + porta_lado * 0.06, piso + 2.15), (1.3, 0.12, 0.14), M.moldura)
    for s in (-1, 1):
        m.caixa((x0 + s * 0.57, yf + porta_lado * 0.06, piso + 1.05), (0.12, 0.12, 2.2), M.moldura)
    if larg >= 5.5:
        for s in (-1, 1):
            janela(m, M, (x0 + s * larg * 0.28, yf, piso + 1.5), 'y', porta_lado, acesa=rng.random() < acesas)
    janela(m, M, (x0, yf, piso + alt + hg * 0.38), 'y', porta_lado, w=0.7, h=0.8, acesa=rng.random() < acesas)
    # Fundos e laterais.
    janela(m, M, (x0, y0 - porta_lado * prof / 2, piso + alt + hg * 0.38), 'y', -porta_lado, w=0.7, h=0.8,
           acesa=rng.random() < acesas)
    nj = max(1, int(prof // 3.2))
    for s in (-1, 1):
        for k in range(nj):
            yy = y0 + (k + 0.5 - nj / 2) * prof / nj
            janela(m, M, (x0 + s * larg / 2, yy, piso + 1.5), 'x', s, acesa=rng.random() < acesas)
    return topo


def casco(m, M, c, L, B, H, pintura, faixa, rz=0.0):
    """Barco de madeira de pesca (færing): casco em U com proa e popa levantadas."""
    c = Vector(c)
    R = Matrix.Rotation(rz, 3, 'Z')
    secoes = []
    for i in range(15):
        t = i / 14
        w = max(0.03, B / 2 * math.sin(math.pi * t) ** 0.55)
        prof = H * (0.55 + 0.45 * math.sin(math.pi * t) ** 0.4)
        borda = H * (0.35 + 0.5 * (2 * t - 1) ** 4)
        anel = []
        for k in range(11):
            f = -math.pi / 2 + math.pi * k / 10
            anel.append(Vector(((t - 0.5) * L, w * math.sin(f), borda - prof * math.cos(f) ** 1.3)))
        anel.append(Vector(((t - 0.5) * L, w * 0.8, borda - H * 0.3)))
        anel.append(Vector(((t - 0.5) * L, -w * 0.8, borda - H * 0.3)))
        secoes.append([c + R @ p for p in anel])
    m.loft(secoes, pintura)
    for s in (-1, 1):
        pts = []
        for i in range(1, 14):
            t = i / 14
            w = max(0.03, B / 2 * math.sin(math.pi * t) ** 0.55)
            borda = H * (0.35 + 0.5 * (2 * t - 1) ** 4)
            pts.append(c + R @ Vector(((t - 0.5) * L, s * (w + 0.015), borda - 0.08)))
        for p, q in zip(pts, pts[1:]):
            m.viga(p, q, 0.05, 0.14, faixa)
    m.caixa(c + R @ Vector((0, 0, H * 0.15)), (0.3, B * 0.8, 0.08), M.cais, rz=rz)


def dragao(m, M, base, d, s=1.0):
    """Cabeça de dragão nas pontas da cumeeira: pescoço curvo para fora e para cima."""
    base, d = Vector(base), Vector(d).normalized()
    pts = [base + d * (1.7 * s * t) + Vector((0, 0, s * (0.15 * t + 1.3 * t ** 2.2))) for t in np.linspace(0, 1, 7)]
    for i, (p, q) in enumerate(zip(pts, pts[1:])):
        e = 0.26 * s * (1 - i / 7)
        m.viga(p, q, e, e * 1.2, M.alcatrao)
    ponta = pts[-1]
    m.viga(ponta, ponta + d * 0.45 * s + Vector((0, 0, -0.1 * s)), 0.1 * s, 0.14 * s, M.alcatrao)
    m.viga(ponta, ponta + d * 0.35 * s + Vector((0, 0, 0.18 * s)), 0.08 * s, 0.1 * s, M.alcatrao)


def cruz(m, M, c, alt=1.2, eixo='y'):
    c = Vector(c)
    m.caixa(c + Vector((0, 0, alt / 2)), (0.14, 0.14, alt), M.alcatrao)
    s = (0.14, alt * 0.55, 0.14) if eixo == 'y' else (alt * 0.55, 0.14, 0.14)
    m.caixa(c + Vector((0, 0, alt * 0.68)), s, M.alcatrao)


def telhado_duas_aguas(m, mat, x0, y0, z_beiral, larg, comp, inclin, beiral=0.4, esp=0.25, eixo='y'):
    """Duas águas com cumeeira ao longo de y (ou x); devolve a altura da cumeeira."""
    a = rad(inclin)
    hg = larg / 2 * math.tan(a)
    ws = (larg / 2 + beiral) / math.cos(a)
    topo = z_beiral + hg
    for s in (-1, 1):
        off = s * (ws / 2 * math.cos(a) - 0.02)
        cz = topo - ws / 2 * math.sin(a) + esp * 0.6
        if eixo == 'y':
            m.caixa((x0 + off, y0, cz), (ws, comp + 2 * beiral, esp), mat, ry=s * a)
        else:
            m.caixa((x0, y0 + off, cz), (comp + 2 * beiral, ws, esp), mat, rx=-s * a)
    return topo


# ============================================================ construções
def construir_farol(M):
    raiz = vazio('Farol')
    rng = random.Random(3)
    # Ilhota: icosfera achatada, deformada por ruído, com um platô para a torre e a casa.
    rocha = Malha('Farol_Rocha')
    bmesh.ops.create_icosphere(rocha.bm, subdivisions=5, radius=1.0)
    for v in rocha.bm.verts:
        p = v.co.copy()
        n = noise.noise(p * 1.7 + Vector((3.1, 0, 0))) * 0.25 + noise.noise(p * 5.3) * 0.07
        v.co = Vector((p.x * 17, p.y * 13, p.z * 7)) * (1 + n)
        v.co.z -= 2.8
        plat = (v.co.x - 2.5) ** 2 / 90 + (v.co.y - 0.5) ** 2 / 45
        if plat < 1 and v.co.z > 2.4:
            v.co.z = 2.4 + (v.co.z - 2.4) * 0.12 + noise.noise(v.co * 0.8) * 0.12
        if v.co.z < -3:
            v.co.z = -3 - (-3 - v.co.z) * 0.3
    rocha.bm.normal_update()
    rocha._marca(0, M.rocha)
    for f in rocha.bm.faces:
        f.smooth = True
    rocha.objeto(raiz)

    m = Malha('Farol_Casas')
    # Base de concreto, torre vermelha com faixa branca, galeria e lanterna.
    m.cilindro((0, 0, 1.6), (0, 0, 4.2), 3.1, 2.9, M.concreto, seg=24)
    for i in range(4):
        m.caixa((0, -3.4 - i * 0.45, 3.9 - i * 0.55), (1.6, 0.5, 0.55), M.concreto)
    m.cilindro((0, 0, 4.2), (0, 0, 10.0), 2.3, 1.98, M.ferro, seg=24)
    m.cilindro((0, 0, 10.0), (0, 0, 12.4), 1.98, 1.83, M.moldura, seg=24)
    m.cilindro((0, 0, 12.4), (0, 0, 17.0), 1.83, 1.58, M.ferro, seg=24)
    for z, r in ((4.2, 2.36), (10.0, 2.03), (12.4, 1.88)):
        m.cilindro((0, 0, z - 0.08), (0, 0, z + 0.08), r, r, M.metal, seg=24)
    m.caixa((0, -2.3, 5.3), (1.0, 0.3, 2.1), M.porta)
    m.caixa((0, -2.37, 6.45), (1.3, 0.25, 0.16), M.moldura)
    for z, ang in ((8.0, 0.0), (14.4, 0.0), (11.2, math.pi)):
        r = 2.1 - (z - 4) * 0.035
        c = Vector((math.sin(ang) * r, -math.cos(ang) * r, z))
        m.caixa(c, (0.55, 0.3, 0.8), M.luz if z > 12 else M.vidro, rz=ang)
    # Galeria com mãos-francesas e guarda-corpo.
    m.cilindro((0, 0, 17.0), (0, 0, 17.3), 2.7, 2.7, M.metal, seg=24)
    for k in range(12):
        a = k / 12 * math.tau
        d = Vector((math.cos(a), math.sin(a), 0))
        m.viga(d * 1.6 + Vector((0, 0, 16.0)), d * 2.55 + Vector((0, 0, 17.0)), 0.1, 0.12, M.metal)
    n = 20
    pts = [Vector((math.cos(k / n * math.tau) * 2.6, math.sin(k / n * math.tau) * 2.6, 0)) for k in range(n)]
    for k, p in enumerate(pts):
        m.cilindro(p + Vector((0, 0, 17.3)), p + Vector((0, 0, 18.35)), 0.035, 0.035, M.metal, seg=6)
        q = pts[(k + 1) % n]
        for z in (17.85, 18.35):
            m.viga(p + Vector((0, 0, z)), q + Vector((0, 0, z)), 0.05, 0.06, M.metal)
    m.cilindro((0, 0, 17.3), (0, 0, 18.3), 1.45, 1.45, M.ferro, seg=24)
    for k in range(10):
        a = k / 10 * math.tau
        p = Vector((math.cos(a) * 1.33, math.sin(a) * 1.33, 0))
        m.cilindro(p + Vector((0, 0, 18.3)), p + Vector((0, 0, 20.4)), 0.05, 0.05, M.metal, seg=6)
    m.cilindro((0, 0, 18.3), (0, 0, 18.4), 1.4, 1.4, M.metal, seg=24)
    m.cilindro((0, 0, 20.3), (0, 0, 20.5), 1.5, 1.5, M.metal, seg=24)
    m.cilindro((0, 0, 20.5), (0, 0, 21.9), 1.65, 0.25, M.ferro, seg=24)
    m.esfera((0, 0, 22.1), 0.32, M.metal)
    m.cilindro((0, 0, 22.3), (0, 0, 23.6), 0.04, 0.02, M.metal, seg=6)
    # Casa do faroleiro no platô e depósito de barco.
    casa(m, M, 6.6, 1.2, 2.9, 5.4, 7.2, 2.8, M.branco, M.telha_verm, inclin=40, palafitas=False,
         acesas=0.7, rng=rng, porta_lado=-1)
    casa(m, M, -4.5, 4.8, 2.7, 3.6, 4.2, 2.2, M.falu, M.telha, inclin=35, palafitas=False,
         acesas=0.0, rng=rng, chamine=False, porta_lado=1)
    # Mastro da bandeira e cerca branca à volta do platô.
    m.cilindro((10.5, -3.5, 2.4), (10.5, -3.5, 10.0), 0.07, 0.04, M.moldura, seg=6)
    cerca = [Vector((2.5 + 9.3 * math.cos(a), 0.5 + 6.6 * math.sin(a), 2.45)) for a in np.linspace(0.2, math.tau - 0.9, 26)]
    for p, q in zip(cerca, cerca[1:]):
        m.cilindro(p, p + Vector((0, 0, 1.0)), 0.05, 0.05, M.moldura, seg=5)
        for z in (0.45, 0.9):
            m.viga(p + Vector((0, 0, z)), q + Vector((0, 0, z)), 0.05, 0.1, M.moldura)
    corpo = m.objeto(raiz)

    vidro = Malha('Farol_Vidro')
    vidro.cilindro((0, 0, 18.35), (0, 0, 20.35), 1.3, 1.3, M.lanterna, seg=24)
    vidro.objeto(raiz)
    lamp = Malha('Farol_Lampada')
    lamp.esfera((0, 0, 19.35), 0.42, M.lampada, seg=16)
    lamp.objeto(raiz)
    return raiz, corpo


def construir_vila(M):
    """Rorbuer lado a lado sobre palafitas, fachadas para a água (-y), cais e píer."""
    raiz = vazio('Vila')
    rng = random.Random(11)
    m = Malha('Vila_Casas')
    piso = 2.0
    casas = [
        (-17.0, 6.0, 9.0, 3.0, M.falu, M.turfa),
        (-8.8, 6.6, 10.5, 3.5, M.ocre, M.telha),
        (-0.6, 6.0, 8.5, 3.0, M.falu, M.turfa),
        (8.2, 7.2, 10.5, 3.7, M.branco, M.telha),
        (17.2, 6.2, 9.5, 3.2, M.falu, M.turfa),
        (25.2, 5.4, 8.0, 2.8, M.ocre, M.turfa),
    ]
    for x, larg, prof, alt, parede, telhado in casas:
        casa(m, M, x, -6 + prof / 2, piso, larg, prof, alt, parede, telhado,
             inclin=rng.uniform(34, 40), rng=rng, acesas=0.55)
    # Cais corrido na frente das casas e píer para os barcos.
    m.caixa((4.1, -9.0, piso - 0.2), (47, 6.0, 0.3), M.cais)
    m.caixa((6.0, -17.5, piso - 0.3), (3.4, 11, 0.3), M.cais)
    for x in np.arange(-19, 28, 3.1):
        for y in (-11.8, -6.2):
            m.cilindro((x, y, -5), (x, y, piso - 0.35), 0.18, 0.18, M.estaca, seg=8)
    for y in np.arange(-12, -23.5, -2.8):
        for x in (4.4, 7.6):
            m.cilindro((x, y, -5), (x, y, piso - 0.45), 0.18, 0.18, M.estaca, seg=8)
    for x in np.arange(-18, 28, 7.5):
        m.cilindro((x, -11.6, piso - 0.1), (x, -11.6, piso + 0.45), 0.16, 0.12, M.metal, seg=8)
    for y in (-15, -19, -22.5):
        for x in (4.5, 7.5):
            m.cilindro((x, y, piso - 0.2), (x, y, piso + 0.35), 0.15, 0.11, M.metal, seg=8)
    # Caixas de peixe e barris no cais.
    for k in range(9):
        x = rng.uniform(-18, 26)
        y = rng.uniform(-10.5, -7.2)
        if rng.random() < 0.5:
            m.cilindro((x, y, piso - 0.05), (x, y, piso + 0.85), 0.34, 0.34, M.porta if k % 2 else M.falu, seg=10)
        else:
            for h in range(rng.randint(1, 3)):
                m.caixa((x, y, piso + 0.2 + h * 0.4), (1.0, 0.6, 0.38), M.branco if h % 2 else M.cais,
                        rz=rng.uniform(-0.2, 0.2))
    # Barcos atracados.
    casco(m, M, (1.8, -17.0, 0.0), 6.8, 2.1, 1.0, M.branco, M.falu, rz=math.pi / 2 + 0.05)
    casco(m, M, (10.2, -19.5, 0.0), 5.6, 1.9, 0.9, M.porta, M.moldura, rz=math.pi / 2 - 0.08)
    casco(m, M, (-12.0, -15.0, 0.0), 5.0, 1.7, 0.8, M.falu, M.moldura, rz=0.25)
    corpo = m.objeto(raiz)
    return raiz, corpo


def construir_igreja(M):
    """Stavkirke inspirada em Borgund: galeria baixa, nave alta, torre e dragões."""
    raiz = vazio('Igreja')
    rng = random.Random(5)
    # Pedestal de rocha que desce pela encosta (no jogo usa o mesmo material do relevo).
    rocha = Malha('Igreja_Rocha')
    bmesh.ops.create_cube(rocha.bm, size=1.0)
    bmesh.ops.subdivide_edges(rocha.bm, edges=rocha.bm.edges[:], cuts=9, use_grid_fill=True)
    for v in rocha.bm.verts:
        p = v.co.copy()
        z = (p.z + 0.5) * 16 - 15.6  # de -15,6 a 0,4
        esp = 1 + max(0, -z) * 0.07
        n = noise.noise(Vector((p.x * 3, p.y * 3, z * 0.25))) * 0.08
        v.co = Vector((p.x * 17 * esp * (1 + n), p.y * 24 * esp * (1 + n), z + (n * 2 if z < 0 else 0)))
    rocha.bm.normal_update()
    rocha._marca(0, M.rocha)
    rocha.objeto(raiz)

    m = Malha('Igreja_Madeira')
    z0 = 0.4
    # Galeria coberta (svalgang) em volta de tudo.
    GX, GY, gz = 11.0, 15.0, 2.6
    m.caixa((0, 0, z0 + gz / 2), (GX, GY, gz), M.alcatrao)
    for k in range(-6, 7):
        for s in (-1, 1):
            m.caixa((s * (GX / 2 + 0.02), k * GY / 14, z0 + 1.3), (0.1, 0.5, 0.9), M.luz if rng.random() < 0.45 else M.vidro)
    # Nave com paredes altas acima da galeria.
    NX, NY, nz = 6.4, 11.0, 8.0
    m.caixa((0, 0, z0 + nz / 2), (NX, NY, nz), M.alcatrao)
    for s in (-1, 1):  # telhado da galeria, em meia-água encostado na nave
        w = (GX - NX) / 2 + 0.6
        a = math.atan2(1.6, w)
        m.caixa((s * (NX / 2 + w / 2 - 0.2), 0, z0 + gz + 0.9), (w / math.cos(a), GY + 0.8, 0.22), M.telhas_igreja, ry=s * a)
        m.caixa((0, s * (NY / 2 + (GY - NY) / 4), z0 + gz + 0.9), (GX + 0.8, (GY - NY) / 2 / math.cos(a) + 0.3, 0.22),
                M.telhas_igreja, rx=-s * a)
    topo = telhado_duas_aguas(m, M.telhas_igreja, 0, 0, z0 + nz, NX, NY, 56, beiral=0.5, esp=0.28)
    hg = topo - (z0 + nz)
    for s in (-1, 1):
        m.prisma([(-NX / 2, 0), (NX / 2, 0), (0, hg)], 0.3, (0, s * (NY / 2 - 0.15), z0 + nz), M.alcatrao)
        # Dragões e cruz nas pontas da cumeeira.
        for lado in (-1, 1):
            dragao(m, M, (lado * 0.2, s * (NY / 2 + 0.55), topo - 0.2), (lado * 0.35, s, 0), s=1.0)
        cruz(m, M, (0, s * (NY / 2 + 0.4), topo + 0.2), alt=1.3)
        # Janelinhas redondas altas, as únicas acesas.
        for x in (-1.4, 1.4):
            m.cilindro((x, s * (NY / 2 - 0.1), z0 + nz - 1.2), (x, s * (NY / 2 + 0.12), z0 + nz - 1.2), 0.38, 0.38,
                       M.luz, seg=12)
    for k in (-3.5, 0, 3.5):
        for s in (-1, 1):
            m.cilindro((s * (NX / 2 - 0.1), k, z0 + nz - 1.5), (s * (NX / 2 + 0.12), k, z0 + nz - 1.5), 0.36, 0.36,
                       M.luz if rng.random() < 0.6 else M.vidro, seg=12)
    # Torre sobre a cumeeira: base, telhados cruzados, campanário e agulha.
    tb = topo - 1.2
    m.caixa((0, 0, tb + 1.3), (2.6, 2.6, 2.6), M.alcatrao)
    tt = telhado_duas_aguas(m, M.telhas_igreja, 0, 0, tb + 2.6, 2.6, 2.6, 55, beiral=0.35, esp=0.2, eixo='y')
    telhado_duas_aguas(m, M.telhas_igreja, 0, 0, tb + 2.6, 2.6, 2.6, 55, beiral=0.35, esp=0.2, eixo='x')
    for s in (-1, 1):
        dragao(m, M, (0, s * 1.65, tt - 0.15), (0, s, 0), s=0.55)
        dragao(m, M, (s * 1.65, 0, tt - 0.15), (s, 0, 0), s=0.55)
    m.caixa((0, 0, tt + 0.6), (1.7, 1.7, 2.0), M.alcatrao)
    for s in (-1, 1):
        m.caixa((0, s * 0.86, tt + 0.8), (1.0, 0.06, 1.0), M.vidro)
        m.caixa((s * 0.86, 0, tt + 0.8), (0.06, 1.0, 1.0), M.vidro)
    m.cilindro((0, 0, tt + 1.6), (0, 0, tt + 8.5), 1.45, 0.05, M.telhas_igreja, seg=8)
    m.cilindro((0, 0, tt + 8.5), (0, 0, tt + 9.3), 0.05, 0.04, M.metal, seg=6)
    m.caixa((0, 0, tt + 9.0), (0.6, 0.05, 0.05), M.metal)
    # Coro e abside a leste (+y), com torrezinha.
    cy = NY / 2 + 2.6
    m.caixa((0, cy, z0 + 2.8), (4.4, 4.0, 5.6), M.alcatrao)
    tc = telhado_duas_aguas(m, M.telhas_igreja, 0, cy, z0 + 5.6, 4.4, 4.0, 55, beiral=0.35, esp=0.22)
    m.prisma([(-2.2, 0), (2.2, 0), (0, tc - z0 - 5.6)], 0.3, (0, cy + 1.85, z0 + 5.6), M.alcatrao)
    ay = cy + 3.4
    m.cilindro((0, ay, z0), (0, ay, z0 + 4.4), 1.9, 1.9, M.alcatrao, seg=12)
    m.cilindro((0, ay, z0 + 4.4), (0, ay, z0 + 6.9), 2.2, 0.6, M.telhas_igreja, seg=12)
    m.cilindro((0, ay, z0 + 6.9), (0, ay, z0 + 7.8), 0.6, 0.6, M.alcatrao, seg=10)
    m.cilindro((0, ay, z0 + 7.8), (0, ay, z0 + 10.2), 0.85, 0.03, M.telhas_igreja, seg=10)
    # Pórtico de entrada a oeste (-y).
    py = -GY / 2 - 1.3
    m.caixa((0, py, z0 + 1.5), (3.0, 2.6, 3.0), M.alcatrao)
    tp = telhado_duas_aguas(m, M.telhas_igreja, 0, py, z0 + 3.0, 3.0, 2.6, 52, beiral=0.3, esp=0.2)
    m.prisma([(-1.5, 0), (1.5, 0), (0, tp - z0 - 3.0)], 0.3, (0, py - 1.15, z0 + 3.0), M.alcatrao)
    m.caixa((0, py - 1.32, z0 + 1.2), (1.3, 0.1, 2.3), M.porta)
    cruz(m, M, (0, py - 1.2, tp + 0.1), alt=0.9)
    corpo = m.objeto(raiz)
    return raiz, corpo


# ============================================================ cozimento
def cozinhar(ob, tam, chao=None):
    """Cozinha cor × oclusão e emissão numa textura; troca os materiais por um só."""
    cena = bpy.context.scene
    cena.render.engine = 'CYCLES'
    cena.cycles.device = 'CPU'
    nome = ob.name
    # UV próprio para o cozimento.
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    me = ob.data
    while me.uv_layers:
        me.uv_layers.remove(me.uv_layers[0])
    me.uv_layers.new(name='cozido')
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.uv.smart_project(angle_limit=rad(60), island_margin=0.004, area_weight=0.0, scale_to_bounds=True)
    bpy.ops.uv.pack_islands(margin=0.004, rotate=True)
    bpy.ops.object.mode_set(mode='OBJECT')

    imgs = {}
    for chave, cs in (('cor', 'sRGB'), ('ao', 'Non-Color'), ('luz', 'sRGB')):
        img = bpy.data.images.new(f'{nome}_{chave}', tam, tam, alpha=False, float_buffer=chave == 'ao')
        img.colorspace_settings.name = cs
        imgs[chave] = img
    nos = []
    for mat in me.materials:
        n = mat.node_tree.nodes.new('ShaderNodeTexImage')
        mat.node_tree.nodes.active = n
        nos.append(n)

    temp = []
    if chao is not None:  # chão provisório só para a oclusão no pé das paredes
        pos = ob.matrix_world.translation
        bpy.ops.mesh.primitive_plane_add(size=chao[1], location=(pos.x, pos.y, pos.z + chao[0]))
        temp.append(bpy.context.active_object)
    bpy.ops.object.select_all(action='DESELECT')
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob

    def assar(tipo, img, amostras, **kw):
        for n in nos:
            n.image = img
        cena.cycles.samples = amostras
        bpy.ops.object.bake(type=tipo, margin=6, margin_type='EXTEND', use_clear=True, **kw)

    amostras_ao = 16 if RAPIDO else 96
    assar('DIFFUSE', imgs['cor'], 4, pass_filter={'COLOR'})
    cena.world.light_settings.distance = 6.0
    assar('AO', imgs['ao'], amostras_ao)
    assar('EMIT', imgs['luz'], 2)
    for t in temp:
        bpy.data.objects.remove(t, do_unlink=True)

    # Cor final = albedo × oclusão suavizada.
    cor = np.array(imgs['cor'].pixels[:], dtype=np.float32).reshape(-1, 4)
    ao = np.array(imgs['ao'].pixels[:], dtype=np.float32).reshape(-1, 4)[:, :1]
    cor[:, :3] *= 0.3 + 0.7 * np.clip(ao, 0, 1) ** 0.8
    final = bpy.data.images.new(f'{nome}_base', tam, tam, alpha=False)
    final.pixels[:] = cor.ravel()
    luz = imgs['luz']

    mat = bpy.data.materials.new(f'{nome}_cozido')
    mat.use_nodes = True
    nt = mat.node_tree
    b = nt.nodes['Principled BSDF']
    b.inputs['Roughness'].default_value = 0.82
    tb = nt.nodes.new('ShaderNodeTexImage')
    tb.image = final
    te = nt.nodes.new('ShaderNodeTexImage')
    te.image = luz
    nt.links.new(tb.outputs['Color'], b.inputs['Base Color'])
    nt.links.new(te.outputs['Color'], b.inputs['Emission Color'])
    b.inputs['Emission Strength'].default_value = 1.0
    me.materials.clear()
    me.materials.append(mat)
    for p in me.polygons:
        p.material_index = 0
    for img in (final, luz):
        img.filepath_raw = os.path.join(bpy.app.tempdir, img.name + '.png')
        img.file_format = 'PNG'
        img.save()
    return mat


def exportar(raizes, caminho):
    bpy.ops.object.select_all(action='DESELECT')
    for r in raizes:
        r.select_set(True)
        for c in r.children_recursive:
            c.select_set(True)
    opcoes = dict(
        filepath=caminho, export_format='GLB', use_selection=True, export_apply=True,
        export_image_format='WEBP', export_image_quality=80, export_yup=True,
        export_texcoords=True, export_normals=True, export_materials='EXPORT',
        export_cameras=False, export_lights=False, export_animations=False,
    )
    draco = dict(export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=10,
                 export_draco_position_quantization=14, export_draco_normal_quantization=10,
                 export_draco_texcoord_quantization=12)
    try:
        bpy.ops.export_scene.gltf(**opcoes, **draco)
    except Exception as erro:  # Blender sem Draco: sai maior, mas funciona igual
        print('Sem compressão Draco:', erro)
        bpy.ops.export_scene.gltf(**opcoes)


# ============================================================ principal
def limpar():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    w = bpy.data.worlds.new('mundo')
    bpy.context.scene.world = w


def principal():
    limpar()
    M = criar_materiais()
    farol, farol_corpo = construir_farol(M)
    vila, vila_corpo = construir_vila(M)
    igreja, igreja_corpo = construir_igreja(M)
    # Separa as construções para uma não sombrear a outra no cozimento.
    farol.location.x = -300
    igreja.location.x = 300
    bpy.context.view_layer.update()

    if '--cartaz' in ARGS:
        import cartaz
        cartaz.renderizar(M, farol, vila, igreja, os.path.join(RAIZ, 'assets', 'cartaz.jpg'), rapido=RAPIDO)

    tam = 512 if RAPIDO else 1024
    cozinhar(farol_corpo, tam)
    cozinhar(vila_corpo, tam, chao=(0.0, 80))
    cozinhar(igreja_corpo, tam, chao=(0.4, 60))
    for r in (farol, vila, igreja):
        r.location = (0, 0, 0)
    saida = os.path.join(RAIZ, 'assets', 'cenario.glb')
    exportar((farol, vila, igreja), saida)
    for ob in (farol_corpo, vila_corpo, igreja_corpo):
        print(f'{ob.name}: {len(ob.data.polygons)} faces')
    print('Exportado:', saida, f'{os.path.getsize(saida) / 1024:.0f} KB')


if __name__ == '__main__':
    sys.path.insert(0, AQUI)
    principal()
