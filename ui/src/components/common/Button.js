import React from "react";
import "./Button.css";
import Tooltip from "./Tooltip";

const Button = ({
  children,
  variant = "primary",
  size = "md",
  icon,
  loading = false,
  disabled = false,
  tooltip,
  className = "",
  ...props
}) => {
  const classes = [
    "ui-button",
    `ui-button--${variant}`,
    `ui-button--${size}`,
    loading && "ui-button--loading",
    className,
  ]
    .filter(Boolean)
    .join(" ");

  const isDisabled = disabled || loading;
  const button = (
    <button className={classes} disabled={isDisabled} {...props}>
      {loading && (
        <span className="ui-button__spinner" aria-label="Loading">
          <svg
            width="16"
            height="16"
            viewBox="0 0 16 16"
            fill="none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <circle
              cx="8"
              cy="8"
              r="7"
              stroke="currentColor"
              strokeWidth="2"
              strokeOpacity="0.3"
            />
            <path
              d="M 8 1 A 7 7 0 0 1 15 8"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
        </span>
      )}
      {!loading && icon && <span className="ui-button__icon">{icon}</span>}
      <span className="ui-button__label">{children}</span>
    </button>
  );

  if (isDisabled && tooltip) {
    return <Tooltip content={tooltip}>{button}</Tooltip>;
  }

  return button;
};

export default Button;

