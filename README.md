# Fenda Boreal

Jogo 3D no navegador feito com [three.js](https://threejs.org/): pilote um planador por uma fenda de cristal sob a aurora boreal.

## Como jogar

Abra `index.html` num navegador moderno (precisa de internet para carregar o three.js do CDN), ou sirva a pasta:

```bash
python3 -m http.server 8000
# depois abra http://localhost:8000
```

| Ação | Controle |
| --- | --- |
| Mover | Mouse, WASD ou setas · arrastar no celular |
| Impulso | Segurar Espaço, Shift ou botão do mouse · botão na tela no celular |
| Pausa | P ou Esc |
| Som | M |

- Colete **fragmentos âmbar**: +50 pontos × multiplicador e recarga do impulso.
- Cada 5 fragmentos seguidos sobem o multiplicador (até ×5); perder um fragmento zera a sequência.
- Desvie de espinhos de cristal, esferas violeta e barreiras de luz. São três escudos.
- A velocidade e a densidade de obstáculos aumentam com a distância. O recorde fica salvo no navegador.

## Visual

- Céu com aurora procedural em shader GLSL (fbm + cortinas animadas) e campo de estrelas.
- Chão de gelo com grade neon em shader, brilhos cintilantes e neblina.
- Paredes de cristal instanciadas (`InstancedMesh`) com wireframe luminoso.
- Pós-processamento com `UnrealBloomPass` e tone mapping ACES.
- Sistema de partículas próprio (rastro, explosões, coleta) com blending aditivo.
- Trilha sonora sintetizada em tempo real com Web Audio.
