import React from 'react';
import {Box} from 'ink';

type CursorAnchorBoxProps = React.ComponentProps<typeof Box> & {
  anchorId: string;
};

export function CursorAnchorBox({
  anchorId,
  ...boxProps
}: CursorAnchorBoxProps): React.JSX.Element {
  // Ink's Box typing doesn't include custom host attributes, so we keep the
  // type escape at this adapter boundary instead of business components.
  const anchoredBoxProps = {
    ...boxProps,
    anchorId,
  } as unknown as React.ComponentProps<typeof Box>;

  return <Box {...anchoredBoxProps} />;
}
