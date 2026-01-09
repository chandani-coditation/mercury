# Design System

This directory contains the centralized design system for the NOC Agent AI frontend. All fonts, spacing, borders, colors, and other design tokens are defined here.

## Quick Start

### Changing Font Sizes Globally

To change font sizes across the entire application:

1. Open `theme.ts`
2. Update the `font.size` section:
   ```typescript
   font: {
     size: {
       xs: "0.875rem",  // Changed from 0.75rem (12px → 14px)
       sm: "1rem",      // Changed from 0.875rem (14px → 16px)
       // ... etc
     }
   }
   ```
3. Update `tailwind.config.js` to match (if using custom font sizes)

### Changing Spacing Globally

To change padding, gaps, or margins:

1. Open `theme.ts`
2. Update the `spacing` section:
   ```typescript
   spacing: {
     cardPadding: "0.75rem",  // Changed from 0.625rem (10px → 12px)
     gapSmall: "0.5rem",      // Changed from 0.375rem (6px → 8px)
     // ... etc
   }
   ```

### Changing Borders Globally

To change border radius or width:

1. Open `theme.ts`
2. Update the `border` section:
   ```typescript
   border: {
     radius: {
       lg: "0.5rem",  // Changed from 0.375rem (6px → 8px)
       // ... etc
     }
   }
   ```

## Usage in Components

### Using Theme Constants Directly

```typescript
import { theme } from "@/design-system";

// Access theme values
const cardPadding = theme.spacing.cardPadding; // "0.625rem"
const fontSize = theme.font.size.xs; // "0.75rem"
const fontFamily = theme.font.family.sans; // "Inter, system-ui, ..."
const fontWeight = theme.font.weight.semibold; // "600"
```

### Using Pre-defined Component Classes

```typescript
import { componentClasses } from "@/design-system";

// Use in JSX
<div className={componentClasses.card}>
  <span className={componentClasses.label}>Label</span>
  <span className={componentClasses.value}>Value</span>
</div>
```

### Using Tailwind Classes (Recommended)

The theme values are designed to work with Tailwind's utility classes:

```typescript
// These classes reference the theme values
<div className="p-2.5 space-y-1.5">  // Uses theme.spacing.cardPadding
  <span className="text-xs font-semibold">  // Uses theme.font.xs
    Content
  </span>
</div>
```

## Available Component Classes

### Card Styles
- `componentClasses.card` - Standard card: `"glass-card p-2.5 space-y-1.5"`
- `componentClasses.cardSmall` - Small card: `"glass-card p-1.5 space-y-0.5"`
- `componentClasses.cardMedium` - Medium card: `"glass-card p-2 space-y-1"`
- `componentClasses.cardLarge` - Large card: `"glass-card p-3 space-y-2"`

### Label Styles
- `componentClasses.label` - Standard label: `"text-xs font-semibold text-muted-foreground"`
- `componentClasses.labelLarge` - Large label: `"text-sm font-semibold text-foreground"`

### Value Styles
- `componentClasses.value` - Standard value: `"text-xs font-semibold text-primary"`
- `componentClasses.valueLarge` - Large value: `"text-sm font-semibold text-primary"`

### Layout Classes
- `componentClasses.grid3Col` - 3-column grid: `"grid grid-cols-3 gap-1.5"`
- `componentClasses.grid2Col` - 2-column grid: `"grid grid-cols-2 gap-1.5"`
- `componentClasses.gridResponsive` - Responsive grid: `"grid grid-cols-1 md:grid-cols-3 gap-2"`
- `componentClasses.flexRow` - Row flex: `"flex items-center gap-1.5"`
- `componentClasses.flexRowTight` - Tight row flex: `"flex items-center gap-1"`

## Migration Guide

When migrating components to use the design system:

1. **Replace hardcoded font sizes:**
   - `text-xs` → Keep as is (already uses theme)
   - `text-sm` → Keep as is
   - Custom sizes → Use `theme.font.size.*` values

2. **Replace hardcoded spacing:**
   - `p-1.5` → `componentClasses.cardSmall` or keep if consistent
   - `p-2.5` → `componentClasses.card`
   - `gap-1.5` → Keep as is (already uses theme)
   - Custom spacing → Use `theme.spacing.*` values

3. **Replace hardcoded borders:**
   - `rounded-sm` → Keep as is (already uses theme)
   - `rounded-lg` → Keep as is
   - Custom radius → Use `theme.border.radius.*` values

4. **Use component classes for common patterns:**
   - Card containers → `componentClasses.card`
   - Labels → `componentClasses.label`
   - Values → `componentClasses.value`

## File Structure

```
design-system/
├── theme.ts          # Main theme constants
├── index.ts          # Exports
└── README.md         # This file
```

## Best Practices

1. **Always use theme constants** instead of hardcoded values
2. **Use component classes** for common patterns (cards, labels, etc.)
3. **Keep Tailwind classes** for one-off styling
4. **Update theme.ts** when you need to change values globally
5. **Document custom values** if they don't fit the theme

## Examples

### Before (Hardcoded)
```typescript
<div className="glass-card p-2.5 space-y-1.5">
  <span className="text-xs font-semibold text-muted-foreground">Label</span>
  <span className="text-xs font-semibold text-primary">Value</span>
</div>
```

### After (Using Component Classes)
```typescript
import { componentClasses } from "@/design-system";

<div className={componentClasses.card}>
  <span className={componentClasses.label}>Label</span>
  <span className={componentClasses.value}>Value</span>
</div>
```

## Future Enhancements

- [ ] Add dark mode theme variants
- [ ] Add animation constants
- [ ] Add responsive breakpoint helpers
- [ ] Add color palette extensions
- [ ] Add typography scale helpers
