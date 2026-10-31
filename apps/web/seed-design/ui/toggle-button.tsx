/**
 * @file ui:toggle-button
 * @requires @seed-design/react@^2.0.0 || ^3.0.0
 **/

import {
  ToggleButton as SeedToggleButton,
  type ToggleButtonProps as SeedToggleButtonProps,
} from "@seed-design/react";
import * as React from "react";
import { LoadingIndicator } from "./loading-indicator";

export interface ToggleButtonProps extends SeedToggleButtonProps {}

/**
 * @see https://seed-design.io/react/components/toggle-button
 * If `asChild` is enabled, manual handling of `LoadingIndicator` is required.
 */
export const ToggleButton = React.forwardRef<
  React.ElementRef<typeof SeedToggleButton>,
  ToggleButtonProps
>(({ loading = false, children, ...otherProps }, ref) => {
  return (
    <SeedToggleButton ref={ref} loading={loading} {...otherProps}>
      {loading && !otherProps.asChild ? <LoadingIndicator>{children}</LoadingIndicator> : children}
    </SeedToggleButton>
  );
});
ToggleButton.displayName = "ToggleButton";

/**
 * This file is a snippet from SEED Design, helping you get started quickly with @seed-design/* packages.
 * You can extend this snippet however you want.
 */
