import {
  type ApplicationConfig,
  LOCALE_ID,
  provideBrowserGlobalErrorListeners,
  provideZoneChangeDetection,
} from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors, withXhr } from '@angular/common/http';
import { authInterceptor } from './auth.interceptor';
import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideZoneChangeDetection({ eventCoalescing: true, runCoalescing: true }),
    { provide: LOCALE_ID, useValue: 'es-CO' },
    provideRouter(routes),
    // zone.js parchea XHR pero no fetch: usar XHR garantiza que las respuestas
    // HTTP disparen la detección de cambios de Angular (incluido el login).
    provideHttpClient(withInterceptors([authInterceptor]), withXhr()),
  ],
};
