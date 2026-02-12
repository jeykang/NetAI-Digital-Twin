/**
 * buildQuery — constructs the QueryContext that Superset sends to the backend.
 *
 * For now this is a pass-through: whatever the user configures in the control
 * panel is forwarded as-is.  Once the Databahn data source is wired in (either
 * as a Superset "database" connection or via a custom REST datasource), this
 * file should be updated to emit the right query shape.
 */
import { buildQueryContext } from '@superset-ui/core';
import { DatabannPipelinesFormData } from '../types';

export default function buildQuery(formData: DatabannPipelinesFormData) {
  return buildQueryContext(formData as any, (baseQueryObject: any) => [
    {
      ...baseQueryObject,
    },
  ]);
}
