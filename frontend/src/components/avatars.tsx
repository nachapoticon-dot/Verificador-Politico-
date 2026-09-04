// Faro, el personaje: un escéptico amable de gafas. El retrato grande preside
// el hero; la mini-cara firma la marca y cada respuesta.

export function FaroAvatar() {
  return (
    <svg
      viewBox="0 0 200 220"
      className="avatar"
      role="img"
      aria-label="Retrato de Faro, un verificador de hechos con gafas y una ceja alzada."
    >
      <path className="sweater" d="M40 220 Q40 158 100 158 Q160 158 160 220 Z" />
      <path className="collar" d="M84 162 Q100 178 116 162 L116 158 L84 158 Z" />
      <rect className="sk" x="90" y="138" width="20" height="26" rx="9" />
      <ellipse className="sk head" cx="100" cy="96" rx="52" ry="56" />
      <circle className="sk" cx="48" cy="100" r="9" />
      <circle className="sk" cx="152" cy="100" r="9" />
      <path
        className="hair"
        d="M48 86 Q50 36 100 34 Q150 36 152 86 Q150 70 134 62 Q150 58 146 50 Q120 40 100 41 Q66 40 54 54 Q49 70 48 86 Z"
      />
      <g className="gafas">
        <circle className="lens" cx="76" cy="98" r="21" />
        <circle className="lens" cx="124" cy="98" r="21" />
        <path className="frame" d="M97 95 q3 -4 6 0" />
        <path className="frame" d="M55 96 L44 99" />
        <path className="frame" d="M145 96 L156 99" />
      </g>
      <path className="ceja" d="M62 70 q14 -7 28 -2" />
      <path className="ceja ceja--alta" d="M112 64 q14 -6 28 1" />
      <g className="ojos">
        <circle className="eye" cx="76" cy="99" r="4.4" />
        <circle className="eye" cx="124" cy="99" r="4.4" />
      </g>
      <path className="nariz" d="M100 104 l-4 16 l8 0" />
      <path className="boca" d="M82 132 q18 11 36 -1" />
    </svg>
  );
}

// Faro trabajando: sentado, leyendo, con la pila de lo que ya revisó al lado.
// Ocupa el hueco de la espera, que antes era una caja de traza y nada más.
export function FaroLeyendo() {
  return (
    <svg
      viewBox="0 0 260 190"
      className="leyendo"
      role="img"
      aria-label="Faro, sentado a una mesa, leyendo un libro junto a una pila de fuentes ya revisadas."
    >
      <path className="mesa" d="M10 177 H250" />

      {/* Lo ya revisado se acumula: la pila crece con la investigación. */}
      <g className="pila">
        <rect className="libro libro-a" x="20" y="161" width="76" height="15" rx="2.5" />
        <rect className="libro libro-b" x="27" y="146" width="62" height="15" rx="2.5" />
        <rect className="libro libro-c" x="34" y="131" width="48" height="15" rx="2.5" />
      </g>

      <g className="figura">
        <path className="sweater" d="M114 177 Q114 127 163 127 Q212 127 212 177 Z" />
        <path className="collar" d="M150 131 Q163 145 176 131 L176 127 L150 127 Z" />
        <rect className="sk" x="153" y="104" width="20" height="28" rx="9" />
        <g className="cabeza">
          <ellipse className="sk" cx="163" cy="72" rx="42" ry="45" />
          <circle className="sk" cx="121" cy="74" r="7.5" />
          <circle className="sk" cx="205" cy="74" r="7.5" />
          {/* Melena maciza con el flequillo bajando hasta cerca de las cejas.
              Con el borde interior pegado al exterior salía una diadema sobre
              una calva, que no es Faro. */}
          <path
            className="hair"
            d="M121 72 Q119 26 163 22 Q207 26 205 72 Q201 57 192 51 Q178 41 163 42 Q148 41 134 51 Q125 57 121 72 Z"
          />
          <g className="gafas">
            <circle className="lens" cx="145" cy="76" r="17" />
            <circle className="lens" cx="181" cy="76" r="17" />
            <path className="frame" d="M161 74 q2 -3 4 0" />
            <path className="frame" d="M129 74 L120 77" />
            <path className="frame" d="M197 74 L206 77" />
          </g>
          {/* Cejas bajas y planas: concentración. Alzadas daban sorpresa. */}
          <path className="ceja" d="M134 56 q11 -4 22 -1" />
          <path className="ceja" d="M170 55 q11 -4 22 1" />
          {/* Dos grupos anidados porque parpadeo y barrido son ambos transform:
              en el mismo elemento se pisarían. Fuera parpadea, dentro recorre.
              Las pupilas van al fondo de la lente: mira el libro, no a ti. */}
          <g className="ojos">
            <g className="pupilas">
              <circle className="eye" cx="145" cy="88" r="3.6" />
              <circle className="eye" cx="181" cy="88" r="3.6" />
            </g>
          </g>
          <path className="nariz" d="M163 82 l-3 12 l6 0" />
          {/* Boca en reposo: está leyendo, no saludando. */}
          <path className="boca" d="M154 103 q9 3 18 0" />
        </g>
      </g>

      <g className="abierto">
        <path className="pagina" d="M112 172 L163 146 L163 177 L112 177 Z" />
        <path className="pagina" d="M214 172 L163 146 L163 177 L214 177 Z" />
        <path className="hoja" d="M163 146 L214 172 L214 177 L163 177 Z" />
        <path className="lomo" d="M163 146 V177" />
        <path className="renglones" d="M126 170 L152 160 M132 175 L155 166" />
        <rect className="sk mano" x="101" y="164" width="21" height="14" rx="7" />
        <rect className="sk mano" x="204" y="164" width="21" height="14" rx="7" />
      </g>
    </svg>
  );
}

export function MiniAvatar() {
  return (
    <svg viewBox="0 0 48 48" className="mini-avatar" aria-hidden="true">
      <circle cx="24" cy="23" r="16" className="sk" />
      <path d="M9 22 Q12 7 24 7 Q36 7 39 22 Q31 15 24 15 Q17 15 9 22 Z" className="hair" />
      <circle cx="18" cy="24" r="6.4" className="lens" />
      <circle cx="31" cy="24" r="6.4" className="lens" />
      <path d="M24.2 23 q-.2 -1.2 .6 -1.2" className="frame" />
      <circle cx="18" cy="24" r="1.7" className="eye" />
      <circle cx="31" cy="24" r="1.7" className="eye" />
    </svg>
  );
}
