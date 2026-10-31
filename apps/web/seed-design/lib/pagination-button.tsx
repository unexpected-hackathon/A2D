/**
 * @file lib:pagination-button
 * @requires @seed-design/react@^2.3.0 || ^3.0.0
 * @requires @seed-design/css@^2.6.0 || ^3.0.0
 **/

import { paginationButton } from "@seed-design/css/recipes/pagination-button";
import { Icon } from "@seed-design/react";
import clsx from "clsx";
import * as React from "react";

export interface PaginationButtonProps
  extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "color"> {}

export const PaginationButton = React.forwardRef<HTMLButtonElement, PaginationButtonProps>(
  (props, ref) => {
    const { children, className, ...buttonProps } = props;

    return (
      <button
        ref={ref}
        type="button"
        {...buttonProps}
        className={clsx(paginationButton(), className)}
      >
        <Icon svg={children} />
      </button>
    );
  },
);
PaginationButton.displayName = "PaginationButton";

/**
 * This file is a snippet from SEED Design, helping you get started quickly with @seed-design/* packages.
 * You can extend this snippet however you want.
 */
