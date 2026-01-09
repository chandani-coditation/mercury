/**
 * Centralized Design System Theme
 * 
 * This file contains all design tokens (fonts, spacing, borders, colors, etc.)
 * that are used across the application. Change values here to update the entire UI.
 * 
 * Usage:
 * - Import theme values: `import { theme } from '@/design-system/theme'`
 * - Use in components: `className={theme.spacing.cardPadding}`
 * - Or use Tailwind classes that reference these values
 */

export const theme = {
  // Typography
  font: {
    // Font families
    sans: [
      "Inter",
      "system-ui",
      "-apple-system",
      "Segoe UI",
      "sans-serif",
    ].join(", "),
    mono: [
      "ui-monospace",
      "SFMono-Regular",
      "Menlo",
      "Monaco",
      "Consolas",
      '"Liberation Mono"',
      '"Courier New"',
      "monospace",
    ].join(", "),
    
    // Font sizes (in rem for accessibility)
    xs: "0.75rem",      // 12px
    sm: "0.875rem",    // 14px
    base: "1rem",      // 16px
    lg: "1.125rem",    // 18px
    xl: "1.25rem",     // 20px
    "2xl": "1.5rem",   // 24px
    "3xl": "1.875rem", // 30px
    
    // Font weights
    normal: "400",
    medium: "500",
    semibold: "600",
    bold: "700",
    
    // Line heights
    tight: "1.25",
    normal: "1.5",
    relaxed: "1.75",
  },

  // Spacing (in rem, following 0.25rem = 4px base)
  spacing: {
    // Padding
    cardPadding: "0.625rem",    // 10px / p-2.5
    cardPaddingSmall: "0.375rem", // 6px / p-1.5
    cardPaddingMedium: "0.5rem",  // 8px / p-2
    cardPaddingLarge: "0.75rem",   // 12px / p-3
    cardPaddingXLarge: "1rem",     // 16px / p-4
    
    // Gaps
    gapTight: "0.25rem",    // 4px / gap-1
    gapSmall: "0.375rem",   // 6px / gap-1.5
    gapMedium: "0.5rem",    // 8px / gap-2
    gapLarge: "0.75rem",    // 12px / gap-3
    gapXLarge: "1rem",      // 16px / gap-4
    
    // Vertical spacing
    spaceTight: "0.375rem",   // 6px / space-y-1.5
    spaceSmall: "0.5rem",     // 8px / space-y-2
    spaceMedium: "0.75rem",   // 12px / space-y-3
    spaceLarge: "1rem",       // 16px / space-y-4
    spaceXLarge: "1.5rem",    // 24px / space-y-6
    
    // Margins
    marginTight: "0.25rem",   // 4px
    marginSmall: "0.5rem",    // 8px
    marginMedium: "0.75rem",  // 12px
    marginLarge: "1rem",      // 16px
  },

  // Borders
  border: {
    width: {
      thin: "1px",
      medium: "2px",
      thick: "3px",
    },
    radius: {
      none: "0",
      sm: "0.125rem",    // 2px
      md: "0.25rem",     // 4px
      lg: "0.375rem",    // 6px
      xl: "0.5rem",      // 8px
      "2xl": "0.75rem",  // 12px
      full: "9999px",
    },
    opacity: {
      light: "0.1",
      medium: "0.2",
      heavy: "0.3",
      full: "1",
    },
  },

  // Shadows
  shadow: {
    sm: "0 1px 2px 0 rgba(0, 0, 0, 0.05)",
    md: "0 4px 6px -1px rgba(0, 0, 0, 0.1)",
    lg: "0 10px 15px -3px rgba(0, 0, 0, 0.1)",
    xl: "0 20px 25px -5px rgba(0, 0, 0, 0.1)",
  },

  // Icon sizes
  icon: {
    xs: "0.75rem",    // 12px / w-3 h-3
    sm: "0.875rem",   // 14px / w-3.5 h-3.5
    md: "1rem",       // 16px / w-4 h-4
    lg: "1.25rem",    // 20px / w-5 h-5
    xl: "1.5rem",     // 24px / w-6 h-6
  },

  // Component-specific sizes
  component: {
    // Button heights
    buttonHeight: {
      sm: "2rem",     // 32px / h-8
      md: "2.5rem",   // 40px / h-10
      lg: "3rem",     // 48px / h-12
    },
    
    // Badge sizes
    badgePadding: {
      sm: "0.125rem 0.375rem",  // 2px 6px
      md: "0.25rem 0.5rem",     // 4px 8px
      lg: "0.375rem 0.75rem",   // 6px 12px
    },
    
    // Input heights
    inputHeight: {
      sm: "2rem",
      md: "2.5rem",
      lg: "3rem",
    },
  },

  // Breakpoints (matching Tailwind defaults)
  breakpoint: {
    sm: "640px",
    md: "768px",
    lg: "1024px",
    xl: "1280px",
    "2xl": "1536px",
  },

  // Z-index scale
  zIndex: {
    base: 0,
    dropdown: 1000,
    sticky: 1020,
    fixed: 1030,
    modalBackdrop: 1040,
    modal: 1050,
    popover: 1060,
    tooltip: 1070,
  },

  // Transitions
  transition: {
    fast: "0.15s ease",
    normal: "0.2s ease",
    slow: "0.3s ease",
  },
} as const;

/**
 * Helper function to get Tailwind class names from theme values
 * This allows us to use theme values in className strings
 */
export const getThemeClasses = {
  // Typography
  textXs: "text-xs",
  textSm: "text-sm",
  textBase: "text-base",
  textLg: "text-lg",
  textXl: "text-xl",
  
  // Spacing
  pCard: "p-2.5",
  pCardSmall: "p-1.5",
  pCardMedium: "p-2",
  pCardLarge: "p-3",
  pCardXLarge: "p-4",
  
  gapTight: "gap-1",
  gapSmall: "gap-1.5",
  gapMedium: "gap-2",
  gapLarge: "gap-3",
  gapXLarge: "gap-4",
  
  spaceTight: "space-y-1.5",
  spaceSmall: "space-y-2",
  spaceMedium: "space-y-3",
  spaceLarge: "space-y-4",
  
  // Borders
  roundedSm: "rounded-sm",
  roundedMd: "rounded-md",
  roundedLg: "rounded-lg",
  roundedXl: "rounded-xl",
  
  // Icons
  iconXs: "w-3 h-3",
  iconSm: "w-3.5 h-3.5",
  iconMd: "w-4 h-4",
  iconLg: "w-5 h-5",
  iconXl: "w-6 h-6",
} as const;

/**
 * Common component class combinations
 * Use these for consistent styling across components
 */
export const componentClasses = {
  // Card styles
  card: "glass-card p-2.5 space-y-1.5",
  cardSmall: "glass-card p-1.5 space-y-0.5",
  cardMedium: "glass-card p-2 space-y-1",
  cardLarge: "glass-card p-3 space-y-2",
  
  // Borderless card styles (for cleaner grid layouts)
  cardBorderless: "p-2.5 space-y-1.5",
  cardSmallBorderless: "p-1.5 space-y-0.5",
  cardMediumBorderless: "p-2 space-y-1",
  cardLargeBorderless: "p-3 space-y-2",
  
  // Label styles
  label: "text-xs font-semibold text-muted-foreground",
  labelLarge: "text-sm font-semibold text-foreground",
  
  // Value styles - Consistent font across all values
  value: "text-xs font-semibold text-primary font-sans", // Standard value font
  valueLarge: "text-sm font-semibold text-primary font-sans", // Large value font
  valueMono: "text-xs font-semibold text-primary font-mono", // Monospace for codes/IDs
  
  // Section headers
  sectionHeader: "text-xs font-semibold text-foreground",
  sectionHeaderLarge: "text-sm font-semibold text-foreground",
  
  // Grid layouts
  grid3Col: "grid grid-cols-3 gap-1.5",
  grid2Col: "grid grid-cols-2 gap-1.5",
  gridResponsive: "grid grid-cols-1 md:grid-cols-3 gap-2",
  
  // Flex layouts
  flexRow: "flex items-center gap-1.5",
  flexRowTight: "flex items-center gap-1",
  flexCol: "flex flex-col gap-1.5",
} as const;
