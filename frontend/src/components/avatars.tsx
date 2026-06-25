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
