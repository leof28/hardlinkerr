## 2026-07-16 - Proper form labeling for screen readers
**Learning:** In React components wrapping inputs, screen readers require explicit `id` and `htmlFor` attributes connecting the label to the input to correctly identify and read the field name.
**Action:** Always ensure custom React input wrappers explicitly map `htmlFor` and `id` when generating dynamic forms.

## 2024-05-18 - [Escape Key Modals]
**Learning:** Added `Escape` key close functionality to React modals for better keyboard accessibility and UX. Discovered that when nesting modals (e.g., a confirm dialog inside a detail modal), it is crucial to manage focus and event propagation so that pressing `Escape` only closes the topmost modal, avoiding unintended complete closures.
**Action:** When implementing `Escape` key listeners for nested UI components, always ensure conditional checks (like checking if a child confirm dialog is active) are in place to prevent closing underlying parent components unintentionally.

