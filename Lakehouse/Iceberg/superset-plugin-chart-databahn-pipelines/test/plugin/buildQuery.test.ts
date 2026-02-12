import buildQuery from '../../src/plugin/buildQuery';

describe('buildQuery', () => {
  it('returns a QueryContext with queries array', () => {
    const formData = {
      datasource: '1__table',
      display_mode: 'summary_table' as const,
    };
    const result = buildQuery(formData as any);
    expect(result).toBeDefined();
    expect(result.queries).toBeDefined();
    expect(Array.isArray(result.queries)).toBe(true);
  });
});
