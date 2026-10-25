# Punto — Dirección visual

## Idea

Una calculadora compacta que se siente como una herramienta de escritorio: el resultado manda y la cinta de cálculo conserva el contexto.

## Sistema

- **Paleta:** azul tinta (`#101c36`) para la herramienta, papel (`#f4f2eb`) para el entorno, lima (`#c8f169`) para operadores y coral (`#ff806d`) para confirmar.
- **Tipografía:** DM Sans para lectura y Space Mono para números, teclas y metadatos.
- **Forma:** paneles de esquinas suaves, controles sólidos y líneas finas; la profundidad se reserva al panel principal.
- **Estados:** el foco usa coral, las acciones operatorias usan lima y el historial aparece como cinta vertical.

## Responsive

En escritorio la calculadora y la cinta comparten el primer viewport. En pantallas estrechas se apilan, manteniendo el teclado en una cuadrícula de cuatro columnas.

## Accesibilidad

HTML semántico, `aria-live` para display e historial, foco visible, soporte de teclado y respeto por `prefers-reduced-motion`.
