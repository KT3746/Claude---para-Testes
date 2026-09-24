# Fenda Boreal

Jogo 3D no navegador feito com [three.js](https://threejs.org/): pilote um planador elétrico rente à água de um fiorde norueguês ao pôr do sol, passando por portões de corrida aérea e desviando de rochas e cabos de alta tensão.

## Como jogar

Sirva a pasta por HTTP (a textura da água não carrega via `file://`) e abra no navegador. É preciso internet para carregar o three.js do CDN.

```bash
python3 -m http.server 8000
# depois abra http://localhost:8000
```

| Ação | Controle |
| --- | --- |
| Pilotar | Mouse, WASD ou setas · arrastar o dedo em qualquer lugar no celular |
| Motor | Segurar Espaço, Shift ou botão do mouse · botão Motor no celular |
| Pausa | P ou Esc |
| Som | M |

- Passe entre os dois pilares laranja de cada portão: +100 pontos × multiplicador e recarga da bateria.
- A cada 4 portões seguidos o multiplicador sobe (até ×5); perder um portão zera a sequência.
- Desvie das rochas no mar e dos cabos de alta tensão. As asas têm 12 m de envergadura e contam na colisão.
- Três vidas. Velocidade e densidade de obstáculos aumentam com a distância. O recorde fica salvo no navegador.

## Visual

- Céu físico (modelo de Preetham, `Sky`) com sol baixo; a luz ambiente e os reflexos vêm de um mapa de ambiente gerado a partir desse céu.
- Água com reflexo real da cena e mapa de normais animado (`Water`).
- Relevo do fiorde gerado por ruído em blocos que se renovam; rocha, musgo, neve e rocha molhada escolhidos no shader por altura e inclinação, com relevo fino por ruído 3D.
- Névoa de perspectiva aérea que usa a cor do céu na direção do olhar.
- Planador modelado com perfil de asa NACA, cauda em T, canopy de vidro e hélice elétrica no nariz.
- Sombras do sol, MSAA, bloom leve, tone mapping ACES e qualidade adaptativa para aparelhos mais fracos.
- Som sintetizado: vento que acompanha a velocidade, motor elétrico e bipes de cronometragem.

## Créditos

- `assets/waternormals.jpg`: do repositório do [three.js](https://github.com/mrdoob/three.js) (licença MIT).
