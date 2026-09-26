import React from 'react';
import ReactECharts from 'echarts-for-react';
import { useTheme } from '../theme';

// ECharts draws on canvas and cannot read CSS variables: switch its built-in theme with ours.
export default function Chart({ option, ...rest }) {
  const theme = useTheme();
  const dark = theme === 'dark';
  return (
    <ReactECharts key={theme} theme={dark ? 'dark' : undefined}
      option={dark ? { backgroundColor: 'transparent', ...option } : option} {...rest} />
  );
}
