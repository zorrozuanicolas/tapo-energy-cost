/**
 * The time zone the screen uses to decide what "today" is. It has to be known before the first request,
 * so it is a build-time setting. It must match the backend's `TIMEZONE`.
 */
export const TIMEZONE = import.meta.env.VITE_TIMEZONE || "America/Montevideo"; // `||`: an empty value falls back too
