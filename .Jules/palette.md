## 2026-07-16 - Proper form labeling for screen readers
**Learning:** In React components wrapping inputs, screen readers require explicit `id` and `htmlFor` attributes connecting the label to the input to correctly identify and read the field name.
**Action:** Always ensure custom React input wrappers explicitly map `htmlFor` and `id` when generating dynamic forms.

## 2024-05-18 - [Escape Key Modals]
**Learning:** Added `Escape` key close functionality to React modals for better keyboard accessibility and UX. Discovered that when nesting modals (e.g., a confirm dialog inside a detail modal), it is crucial to manage focus and event propagation so that pressing `Escape` only closes the topmost modal, avoiding unintended complete closures.
**Action:** When implementing `Escape` key listeners for nested UI components, always ensure conditional checks (like checking if a child confirm dialog is active) are in place to prevent closing underlying parent components unintentionally.

## $(date +%Y-%m-%d) - [Disabled Button Visibility]
**Learning:** In standalone React setups using inline CSS (e.g. style={{...}}), global disabled states for buttons must use !important to guarantee they override inline styles that define default interactivity (like cursors and backgrounds), preventing visual confusion.
**Action:** When adding base stylistic state rules (like :disabled or :hover) in a heavily inline-styled environment, enforce them via !important to ensure UX consistency.

## 2026-07-30 - Toast Notification Accessibility
**Learning:** For dynamic, transient notifications like Toast messages, adding `aria-live="polite"` and `aria-atomic="true"` to the container guarantees screen readers announce them properly without immediately breaking user focus. Combining this with dynamic roles (e.g. `role="alert"` for errors and `role="status"` for info/success) ensures critical information reaches non-visual users reliably.
**Action:** When implementing toast or snackbar components, always provide an `aria-live` region wrapping the notification map, and apply semantic `role` attributes based on the severity.

## 2026-07-31 - [Visual Loading States]
**Learning:** Relying solely on text changes (like '...') or color changes to indicate loading state on buttons is a missed UX opportunity. Users often miss text changes on buttons they just clicked.
**Action:** Use an SVG spinner component in addition to text changes when a button is in a loading/running state. Wrap the button content with `display: inline-flex` and `alignItems: center` to vertically align the spinner alongside the text.
## 2024-05-18 - [Add loading spinners to refresh buttons]
**Learning:** When async buttons replace their entire text with a generic loading string, it causes layout shifts and removes context from what the button is currently doing. Using an inline SVG spinner alongside the original text with a small gap preserves the layout and improves UX.
**Action:** Use inline SVG spinners and 'display: inline-flex' alongside the original text for loading states to maintain context and prevent layout shifts.
## $(date +%Y-%m-%d) - [Tab Accessibility]
**Learning:** Custom tab implementations lacking standard ARIA attributes (`role="tablist"`, `role="tab"`, `aria-selected`, `aria-controls`) completely break the structural meaning for screen reader users, treating them simply as isolated groups of buttons without clear association to the currently visible content panel.
**Action:** When building custom tab interfaces, always apply `role="tablist"` to the container, `role="tab"` and `aria-selected` to the tab buttons, and wrap the visible content area in a `role="tabpanel"` linked via `aria-labelledby` to the active tab ID.
