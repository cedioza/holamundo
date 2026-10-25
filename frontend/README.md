# Frontend

This project was generated using [Angular CLI](https://github.com/angular/angular-cli) version 22.2.3.

## Sistema de diseño

La interfaz sigue el diseño de Figma (`BmrarQx9NA5STj2lR4n9EB`). Los tokens viven como variables CSS en `src/styles.scss` y las piezas compuestas (shell, paneles, tablas, campos, acciones) en `src/app/app.scss`.

| Token | Valor | Uso |
| --- | --- | --- |
| `--sidebar` | `#102c54` | Fondo de la navegación lateral |
| `--sidebar-muted` | `#b8c9df` | Texto secundario del lateral |
| `--ink` | `#192b44` | Texto principal |
| `--ink-muted` | `#62738b` | Texto secundario y etiquetas |
| `--primary` | `#205ac7` | Acción primaria y acentos |
| `--border` | `#dfe6ef` | Divisores y contornos |
| `--surface` | `#f8fafd` | Superficie sutil (cabeceras de tabla, campos) |

Tipografía: **Inter** (400/500/600/700/800). Los iconos de Figma se guardan como SVG locales en `public/icons/` y se referencian con rutas absolutas (`/icons/search.svg`); no hay dependencias de recursos externos en tiempo de ejecución.

## Development server

To start a local development server, run:

```bash
ng serve
```

Once the server is running, open your browser and navigate to `http://localhost:4200/`. The application will automatically reload whenever you modify any of the source files.

## Code scaffolding

Angular CLI includes powerful code scaffolding tools. To generate a new component, run:

```bash
ng generate component component-name
```

For a complete list of available schematics (such as `components`, `directives`, or `pipes`), run:

```bash
ng generate --help
```

## Building

To build the project run:

```bash
ng build
```

This will compile your project and store the build artifacts in the `dist/` directory. By default, the production build optimizes your application for performance and speed.

## Running unit tests

To execute unit tests with the [Vitest](https://vitest.dev/) test runner, use the following command:

```bash
ng test
```

## Running end-to-end tests

For end-to-end (e2e) testing, run:

```bash
ng e2e
```

Angular CLI does not come with an end-to-end testing framework by default. You can choose one that suits your needs.

## Additional Resources

For more information on using the Angular CLI, including detailed command references, visit the [Angular CLI Overview and Command Reference](https://angular.dev/tools/cli) page.
