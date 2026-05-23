# Implementation Plan: Dolby-Tool Frontend UI & UX Refactoring

This plan outlines a complete set of visually polished, performant, and native-feeling frontend improvements for the **dolby-tool** single-page web application.

Following the project's engineering philosophy, all animations and layout improvements will be implemented using **pure system-native CSS transitions, transforms, and animations**, with zero external dependencies and zero layout shifts. It is fully optimized for **Safari on macOS** (Apple-native feel).

---

## 1. Goal
Improve the overall visual appeal, responsiveness, and interactive feel of the Dolby-tool web interface (`index.html`, `styles.css`, `app.js`). 

Specifically:
- Add high-fidelity, hardware-accelerated transitions and animations.
- Refine the aesthetic structure (such as a blurred sticky header, polished scrollbars, and tactile hover states).
- Provide a responsive skeleton loading animation during file analysis.
- Animate live incoming events smoothly to make the TV Capture tab feel responsive and modern.
- Refine typography, focus states, and tooltips/toasts.

---

## 2. Current Context & Assumptions
- **Active Files:** 
  - `dolby_tool/web/index.html`
  - `dolby_tool/web/styles.css`
  - `dolby_tool/web/app.js`
- **Environment:** Served via a FastAPI backend on port 7878 using the `uv` environment. Built-in caching is bypassed during development using a version query string (`?v=copy-refactor-20260522`), which we will increment.
- **Constraints:** No NPM/bundler build step, no third-party libraries (e.g. Tailwind, Framer Motion, GSAP, or React). All code must remain lightweight, fast-loading, standard HTML/CSS/JS.

---

## 3. Proposed Approach

### Design Philosophy
- **Safari-Optimized Apple Native Aesthetic:** Deep, dark gray elevator backgrounds, subtle borders, high-performance webkit effects, and elastic cubic-bezier timing.
- **CSS-First Animations:** Leverage the GPU using `transform` (using translation and scaling) and `opacity` rather than animating layout-triggering properties (like `height`, `width`, or `margin`).
- **Zero CLS (Cumulative Layout Shift):** Loading states and skeleton screens should pre-allocate the exact container sizes to prevent structural jumping when data resolves.

---

## 4. Step-by-Step Plan

### Step 4.1: Header & Global Typography Refinement (styles.css)
1. **Semi-Transparent Blurred Header:**
   Change the hard sticky background of `header` to a native iOS/macOS-style frosted glass effect.
   ```css
   header {
     position: sticky;
     top: 0;
     background: rgba(20, 24, 29, 0.85); /* Semitransparent var(--bg-elev) */
     backdrop-filter: blur(16px);
     -webkit-backdrop-filter: blur(16px);
     border-bottom: 1px solid var(--border);
     z-index: 100;
     transition: border-color 0.3s;
   }
   ```
2. **Breathing Logo Dot:**
   Animate the active dot in the header to give the tool a subtle live indicator feel.
   ```css
   header h1 .dot {
     color: var(--accent);
     display: inline-block;
     animation: logoBreathe 3s ease-in-out infinite;
   }
   @keyframes logoBreathe {
     0%, 100% {
       opacity: 1;
       transform: scale(1);
       filter: drop-shadow(0 0 3px rgba(79, 158, 255, 0.6));
     }
     50% {
       opacity: 0.5;
       transform: scale(0.9);
       filter: drop-shadow(0 0 0px transparent);
     }
   }
   ```
3. **Elegant Custom Dark Scrollbars:**
   Establish custom global scrollbar styles for a sleeker appearance, targeting `.events` and raw pre blocks.
   ```css
   ::-webkit-scrollbar {
     width: 8px;
     height: 8px;
   }
   ::-webkit-scrollbar-track {
     background: var(--bg);
   }
   ::-webkit-scrollbar-thumb {
     background: var(--border);
     border-radius: 4px;
     transition: background 0.2s;
   }
   ::-webkit-scrollbar-thumb:hover {
     background: var(--text-dim);
   }
   ```

### Step 4.2: Smooth Tab Transitions (styles.css)
Currently, clicking tabs instantly toggles `display: none` / `display: block`. We can animate this transition seamlessly using CSS keyframes on the `.panel.active` elements.
```css
.panel {
  display: none;
  opacity: 0;
}
.panel.active {
  display: block;
  animation: tabFadeIn 0.25s cubic-bezier(0.16, 1, 0.3, 1) forwards;
}

@keyframes tabFadeIn {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
```

### Step 4.3: Tactile Hover and Click States (styles.css)
1. **Buttons (`.btn`):** Add scaling and slight shadow glow on hover.
   ```css
   .btn {
     /* ... existing properties ... */
     transition: background-color 0.15s ease, border-color 0.15s ease, transform 0.1s ease, box-shadow 0.15s ease;
   }
   .btn:hover:not(:disabled) {
     background: #28303d;
     border-color: var(--accent);
     box-shadow: 0 0 10px rgba(79, 158, 255, 0.15);
   }
   .btn:active:not(:disabled) {
     transform: scale(0.97);
   }
   ```
2. **Cards (`.card`):** Soft lift on hover to enhance spatial hierarchy.
   ```css
   .card {
     /* ... existing properties ... */
     transition: border-color 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
   }
   .card:hover {
     border-color: rgba(79, 158, 255, 0.3);
     transform: translateY(-1px);
     box-shadow: 0 6px 16px rgba(0, 0, 0, 0.25);
   }
   ```
3. **Pills (`.pill`):** Add subtle animated pulse state on warning/success indicators if relevant, or simply polish their static visuals.
4. **Form Inputs:**
   Refine the focus glow transition.
   ```css
   input[type=text] {
     /* ... existing ... */
     transition: border-color 0.2s ease, box-shadow 0.2s ease;
   }
   input[type=text]:focus {
     outline: none;
     border-color: var(--accent);
     box-shadow: 0 0 8px rgba(79, 158, 255, 0.25);
   }
   ```

### Step 4.4: Shimmering Skeleton Loader (styles.css & app.js)
Replace the simple `<h2>Inspecting…</h2>` and `<h2>Comparing…</h2>` cards with a modern shimmering skeleton loader that represents metadata rows.
1. **Shimmer Effect in CSS:**
   ```css
   .skeleton-shimmer {
     background: linear-gradient(
       90deg,
       var(--bg-card) 25%,
       #232b35 37%,
       var(--bg-card) 63%
     );
     background-size: 400% 100%;
     animation: shimmerRun 1.4s ease infinite;
   }
   @keyframes shimmerRun {
     0% { background-position: 100% 50%; }
     100% { background-position: 0% 50%; }
   }
   
   .skeleton-title {
     height: 20px;
     width: 40%;
     border-radius: 4px;
     margin-bottom: 12px;
   }
   .skeleton-line {
     height: 14px;
     width: 100%;
     border-radius: 4px;
     margin-bottom: 8px;
   }
   .skeleton-grid {
     display: grid;
     grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
     gap: 12px 16px;
     margin-top: 16px;
   }
   .skeleton-kv {
     height: 40px;
     border-radius: 6px;
   }
   ```
2. **Implementation in JS:**
   Modify `runInspect` in `app.js` to render a structured skeleton layout:
   ```javascript
   function createSkeletonLoader() {
     return el('div', { class: 'card' },
       el('div', { class: 'skeleton-title skeleton-shimmer' }),
       el('div', { class: 'skeleton-line skeleton-shimmer', style: 'width: 70%' }),
       el('h3', { style: 'color: transparent' }, 'Container'),
       el('div', { class: 'skeleton-grid' },
         el('div', { class: 'skeleton-kv skeleton-shimmer' }),
         el('div', { class: 'skeleton-kv skeleton-shimmer' }),
         el('div', { class: 'skeleton-kv skeleton-shimmer' }),
         el('div', { class: 'skeleton-kv skeleton-shimmer' })
       )
     );
   }
   ```
   Modify `compare-go` to render a table-shaped skeleton during the compare API request.

### Step 4.5: Smooth Scrolling & Sliding Live Events (styles.css)
Live events currently pop into existence instantly. When capturing log activity, we can animate these entries fading and expanding down so they roll in with a smooth native terminal feel.
```css
.event {
  /* ... existing properties ... */
  animation: eventRollIn 0.3s cubic-bezier(0.16, 1, 0.3, 1) forwards;
  overflow: hidden;
  transform-origin: top;
}

@keyframes eventRollIn {
  from {
    opacity: 0;
    transform: translateY(-12px);
    max-height: 0;
    padding-top: 0;
    padding-bottom: 0;
    margin-bottom: 0;
  }
  to {
    opacity: 1;
    transform: translateY(0);
    max-height: 100px; /* high enough to cover any single log item */
    padding-top: 4px;
    padding-bottom: 4px;
    margin-bottom: 2px;
  }
}
```

### Step 4.6: "Copied" Toast and Micro-Interactions (styles.css & app.js)
Ensure the Copy-to-Clipboard status utilizes elastic easing, which makes the toast feel extremely responsive.
```css
.copy-status {
  /* ... existing ... */
  transition: opacity 0.25s cubic-bezier(0.34, 1.56, 0.64, 1), transform 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
}
```
We will check the "Copy full JSON" and copy summary mechanics to make sure there are no other regressions.

---

## 5. Files Likely to Change

All paths are relative to the active workspace `/Users/psp/Development/Dolby`:

| File Path | Description | Type of Modification |
|---|---|---|
| `dolby_tool/web/index.html` | SPA structure, update script/style version tags for cache busting | HTML layout updates |
| `dolby_tool/web/styles.css` | Define animations, frosted header, skeleton shimmer, transitions, scrollbars, list entries | CSS animations & refinements |
| `dolby_tool/web/app.js` | Update loaders to return modern HTML skeleton structure during backend operations | JS DOM updates |

---

## 6. Tests & Validation

1. **Local Launch Verification:**
   - Launch the server locally using the command `./dolby-tool start` (uses uv, python 3.14.5).
   - Navigate to `http://localhost:7878` in Safari.
2. **Feature Tests:**
   - **Inspect Tab:** Drag & drop files. Confirm that the shimmer skeleton shows during parsing, and renders the result properly with tab fadeIn animation.
   - **Compare Tab:** Add multiple files. Confirm score weights form inputs trigger proper hover/focus states, and comparison table displays nicely with smooth active state.
   - **Capture Tab:** Click "Start Capture". Confirm that the pulse running indicator is styled cleanly and that new logs trigger the `eventRollIn` transition gracefully without flickering.
   - **Copy Button:** Verify copying summary cards works as designed (copies formatted JSON to clipboard and pops open the toast) and copies full raw JSON on dropdown click.
3. **UI Consistency Checks:**
   - Verify layout responsiveness on small screens.
   - Ensure `backdrop-filter` is processed cleanly on macOS Safari.

---

## 7. Risks, Trade-offs & Open Questions
- **Performance Impact of Blurred Elements:** Heavy use of `backdrop-filter` can occasionally impact scroll performance on extremely low-end computers. Given that this is a desktop utility running locally on a macOS device, hardware acceleration will render this effortlessly.
- **Max-Height Animation Constraint:** To animate raw text entries, we use `max-height`. An over-estimated `max-height` (e.g., `100px`) might cause a slight delay in the deceleration curve of the animation. We can resolve this by keeping the `max-height` value tight or using scale-up transitions.
- **Cache-Busting Resolution:** Using `?v=ui-refactor-20260523` ensures Safari loads the assets fresh, protecting against stale browser caching issues.
