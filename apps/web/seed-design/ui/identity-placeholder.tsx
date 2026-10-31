/**
 * @file ui:identity-placeholder
 * @requires @seed-design/react@^2.0.0 || ^3.0.0
 **/

import { IdentityPlaceholder as SeedIdentityPlaceholder } from "@seed-design/react";
import * as React from "react";

export interface IdentityPlaceholderProps
  extends Omit<SeedIdentityPlaceholder.RootProps, "children" | "asChild"> {}

/**
 * @see https://seed-design.io/react/components/identity-placeholder
 */
export const IdentityPlaceholder = React.forwardRef<HTMLDivElement, IdentityPlaceholderProps>(
  (props, ref) => {
    return (
      <SeedIdentityPlaceholder.Root {...props} ref={ref}>
        <SeedIdentityPlaceholder.Image />
      </SeedIdentityPlaceholder.Root>
    );
  },
);
IdentityPlaceholder.displayName = "IdentityPlaceholder";

/**
 * This file is a snippet from SEED Design, helping you get started quickly with @seed-design/* packages.
 * You can extend this snippet however you want.
 */
