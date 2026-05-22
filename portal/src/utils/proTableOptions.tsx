import React, { type ReactNode } from 'react';
import { Tooltip } from 'antd';

/** 表格操作列固定宽度 */
export const OPERATION_COL_WIDTH = 140;

const optionTooltipTargetStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
};

type ElementWithChildren = React.ReactElement<{ children?: ReactNode }>;

const wrapTooltipChildren = (children: ReactNode): ReactNode => {
  if (children === null || children === undefined) {
    return children;
  }

  return <span style={optionTooltipTargetStyle}>{children}</span>;
};

const makeTooltipTargetsRefSafe = (node: ReactNode): ReactNode => {
  if (Array.isArray(node)) {
    return node.map(makeTooltipTargetsRefSafe);
  }

  if (!React.isValidElement(node)) {
    return node;
  }

  const element = node as ElementWithChildren;
  const { children } = element.props;
  const nextChildren =
    children === undefined ? children : React.Children.map(children, makeTooltipTargetsRefSafe);

  if (element.type === Tooltip) {
    return React.cloneElement(element, undefined, wrapTooltipChildren(nextChildren));
  }

  if (nextChildren === children) {
    return element;
  }

  return React.cloneElement(element, undefined, nextChildren);
};

export const renderRefSafeTableOptions = (_: unknown, defaultDoms: ReactNode[]) =>
  defaultDoms.map(makeTooltipTargetsRefSafe);
