// URL base del backend, configurable por entorno (VITE_API_URL) en vez de
// hardcodeada — necesario para poder desplegar el frontend en un host
// distinto al backend, o en la app de escritorio empaquetada. Sin la
// variable definida, cae al valor de siempre (dev local).
export const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'
