import { baseApi as api } from "./baseApi";
export const addTagTypes = ["grid"] as const;
const injectedRtkApi = api
  .enhanceEndpoints({
    addTagTypes,
  })
  .injectEndpoints({
    endpoints: (build) => ({
      archiveRowGridRowsRowIdDelete: build.mutation<
        ArchiveRowGridRowsRowIdDeleteApiResponse,
        ArchiveRowGridRowsRowIdDeleteApiArg
      >({
        query: (queryArg) => ({
          url: `/grid/rows/${queryArg.rowId}`,
          method: "DELETE",
        }),
        invalidatesTags: ["grid"],
      }),
      getRowGridRowsRowIdGet: build.query<
        GetRowGridRowsRowIdGetApiResponse,
        GetRowGridRowsRowIdGetApiArg
      >({
        query: (queryArg) => ({ url: `/grid/rows/${queryArg.rowId}` }),
        providesTags: ["grid"],
      }),
      patchRowGridRowsRowIdPatch: build.mutation<
        PatchRowGridRowsRowIdPatchApiResponse,
        PatchRowGridRowsRowIdPatchApiArg
      >({
        query: (queryArg) => ({
          url: `/grid/rows/${queryArg.rowId}`,
          method: "PATCH",
          body: queryArg.rowPatch,
        }),
        invalidatesTags: ["grid"],
      }),
      listTablesGridTablesGet: build.query<
        ListTablesGridTablesGetApiResponse,
        ListTablesGridTablesGetApiArg
      >({
        query: (queryArg) => ({
          url: `/grid/tables`,
          headers: {
            "x-grid-namespace": queryArg["x-grid-namespace"],
          },
        }),
        providesTags: ["grid"],
      }),
      createTableGridTablesPost: build.mutation<
        CreateTableGridTablesPostApiResponse,
        CreateTableGridTablesPostApiArg
      >({
        query: (queryArg) => ({
          url: `/grid/tables`,
          method: "POST",
          body: queryArg.tableCreate,
          headers: {
            "x-grid-namespace": queryArg["x-grid-namespace"],
          },
        }),
        invalidatesTags: ["grid"],
      }),
      describeTableGridTablesSlugGet: build.query<
        DescribeTableGridTablesSlugGetApiResponse,
        DescribeTableGridTablesSlugGetApiArg
      >({
        query: (queryArg) => ({
          url: `/grid/tables/${queryArg.slug}`,
          headers: {
            "x-grid-namespace": queryArg["x-grid-namespace"],
          },
        }),
        providesTags: ["grid"],
      }),
      addColumnGridTablesSlugColumnsPost: build.mutation<
        AddColumnGridTablesSlugColumnsPostApiResponse,
        AddColumnGridTablesSlugColumnsPostApiArg
      >({
        query: (queryArg) => ({
          url: `/grid/tables/${queryArg.slug}/columns`,
          method: "POST",
          body: queryArg.columnCreate,
          headers: {
            "x-grid-namespace": queryArg["x-grid-namespace"],
          },
        }),
        invalidatesTags: ["grid"],
      }),
      addIndexGridTablesSlugIndexesPost: build.mutation<
        AddIndexGridTablesSlugIndexesPostApiResponse,
        AddIndexGridTablesSlugIndexesPostApiArg
      >({
        query: (queryArg) => ({
          url: `/grid/tables/${queryArg.slug}/indexes`,
          method: "POST",
          body: queryArg.indexCreate,
          headers: {
            "x-grid-namespace": queryArg["x-grid-namespace"],
          },
        }),
        invalidatesTags: ["grid"],
      }),
      queryGridTablesSlugQueryPost: build.mutation<
        QueryGridTablesSlugQueryPostApiResponse,
        QueryGridTablesSlugQueryPostApiArg
      >({
        query: (queryArg) => ({
          url: `/grid/tables/${queryArg.slug}/query`,
          method: "POST",
          body: queryArg.body,
          headers: {
            "x-grid-namespace": queryArg["x-grid-namespace"],
          },
        }),
        invalidatesTags: ["grid"],
      }),
      reconcileGridTablesSlugReconcilePost: build.mutation<
        ReconcileGridTablesSlugReconcilePostApiResponse,
        ReconcileGridTablesSlugReconcilePostApiArg
      >({
        query: (queryArg) => ({
          url: `/grid/tables/${queryArg.slug}/reconcile`,
          method: "POST",
          headers: {
            "x-grid-namespace": queryArg["x-grid-namespace"],
          },
        }),
        invalidatesTags: ["grid"],
      }),
      addRelationGridTablesSlugRelationsPost: build.mutation<
        AddRelationGridTablesSlugRelationsPostApiResponse,
        AddRelationGridTablesSlugRelationsPostApiArg
      >({
        query: (queryArg) => ({
          url: `/grid/tables/${queryArg.slug}/relations`,
          method: "POST",
          body: queryArg.relationCreate,
          headers: {
            "x-grid-namespace": queryArg["x-grid-namespace"],
          },
        }),
        invalidatesTags: ["grid"],
      }),
      createRowGridTablesSlugRowsPost: build.mutation<
        CreateRowGridTablesSlugRowsPostApiResponse,
        CreateRowGridTablesSlugRowsPostApiArg
      >({
        query: (queryArg) => ({
          url: `/grid/tables/${queryArg.slug}/rows`,
          method: "POST",
          body: queryArg.rowCreate,
          headers: {
            "x-grid-namespace": queryArg["x-grid-namespace"],
          },
        }),
        invalidatesTags: ["grid"],
      }),
      listLinksGridTablesSlugRowsRowIdLinksGet: build.query<
        ListLinksGridTablesSlugRowsRowIdLinksGetApiResponse,
        ListLinksGridTablesSlugRowsRowIdLinksGetApiArg
      >({
        query: (queryArg) => ({
          url: `/grid/tables/${queryArg.slug}/rows/${queryArg.rowId}/links`,
          headers: {
            "x-grid-namespace": queryArg["x-grid-namespace"],
          },
          params: {
            relation_key: queryArg.relationKey,
          },
        }),
        providesTags: ["grid"],
      }),
      relateGridTablesSlugRowsRowIdRelatePost: build.mutation<
        RelateGridTablesSlugRowsRowIdRelatePostApiResponse,
        RelateGridTablesSlugRowsRowIdRelatePostApiArg
      >({
        query: (queryArg) => ({
          url: `/grid/tables/${queryArg.slug}/rows/${queryArg.rowId}/relate`,
          method: "POST",
          body: queryArg.relateRequest,
          headers: {
            "x-grid-namespace": queryArg["x-grid-namespace"],
          },
        }),
        invalidatesTags: ["grid"],
      }),
      addSectionGridTablesSlugSectionsPost: build.mutation<
        AddSectionGridTablesSlugSectionsPostApiResponse,
        AddSectionGridTablesSlugSectionsPostApiArg
      >({
        query: (queryArg) => ({
          url: `/grid/tables/${queryArg.slug}/sections`,
          method: "POST",
          body: queryArg.sectionCreate,
          headers: {
            "x-grid-namespace": queryArg["x-grid-namespace"],
          },
        }),
        invalidatesTags: ["grid"],
      }),
      listTypesGridTypesGet: build.query<
        ListTypesGridTypesGetApiResponse,
        ListTypesGridTypesGetApiArg
      >({
        query: () => ({ url: `/grid/types` }),
        providesTags: ["grid"],
      }),
    }),
    overrideExisting: false,
  });
export { injectedRtkApi as gridApi };
export type ArchiveRowGridRowsRowIdDeleteApiResponse = unknown;
export type ArchiveRowGridRowsRowIdDeleteApiArg = {
  rowId: string;
};
export type GetRowGridRowsRowIdGetApiResponse =
  /** status 200 Successful Response */ RowOut;
export type GetRowGridRowsRowIdGetApiArg = {
  rowId: string;
};
export type PatchRowGridRowsRowIdPatchApiResponse =
  /** status 200 Successful Response */ RowOut;
export type PatchRowGridRowsRowIdPatchApiArg = {
  rowId: string;
  rowPatch: RowPatch;
};
export type ListTablesGridTablesGetApiResponse =
  /** status 200 Successful Response */ TableOut[];
export type ListTablesGridTablesGetApiArg = {
  "x-grid-namespace"?: string;
};
export type CreateTableGridTablesPostApiResponse =
  /** status 201 Successful Response */ TableOut;
export type CreateTableGridTablesPostApiArg = {
  "x-grid-namespace"?: string;
  tableCreate: TableCreate;
};
export type DescribeTableGridTablesSlugGetApiResponse =
  /** status 200 Successful Response */ TableDescribe;
export type DescribeTableGridTablesSlugGetApiArg = {
  slug: string;
  "x-grid-namespace"?: string;
};
export type AddColumnGridTablesSlugColumnsPostApiResponse =
  /** status 201 Successful Response */ ColumnOut;
export type AddColumnGridTablesSlugColumnsPostApiArg = {
  slug: string;
  "x-grid-namespace"?: string;
  columnCreate: ColumnCreate;
};
export type AddIndexGridTablesSlugIndexesPostApiResponse =
  /** status 201 Successful Response */ IndexOut;
export type AddIndexGridTablesSlugIndexesPostApiArg = {
  slug: string;
  "x-grid-namespace"?: string;
  indexCreate: IndexCreate;
};
export type QueryGridTablesSlugQueryPostApiResponse =
  /** status 200 Successful Response */ QueryResult;
export type QueryGridTablesSlugQueryPostApiArg = {
  slug: string;
  "x-grid-namespace"?: string;
  body: QueryRequest | null;
};
export type ReconcileGridTablesSlugReconcilePostApiResponse =
  /** status 200 Successful Response */ string[];
export type ReconcileGridTablesSlugReconcilePostApiArg = {
  slug: string;
  "x-grid-namespace"?: string;
};
export type AddRelationGridTablesSlugRelationsPostApiResponse =
  /** status 201 Successful Response */ RelationOut;
export type AddRelationGridTablesSlugRelationsPostApiArg = {
  slug: string;
  "x-grid-namespace"?: string;
  relationCreate: RelationCreate;
};
export type CreateRowGridTablesSlugRowsPostApiResponse =
  /** status 201 Successful Response */ RowOut;
export type CreateRowGridTablesSlugRowsPostApiArg = {
  slug: string;
  "x-grid-namespace"?: string;
  rowCreate: RowCreate;
};
export type ListLinksGridTablesSlugRowsRowIdLinksGetApiResponse =
  /** status 200 Successful Response */ RowOut[];
export type ListLinksGridTablesSlugRowsRowIdLinksGetApiArg = {
  slug: string;
  rowId: string;
  relationKey: string;
  "x-grid-namespace"?: string;
};
export type RelateGridTablesSlugRowsRowIdRelatePostApiResponse = unknown;
export type RelateGridTablesSlugRowsRowIdRelatePostApiArg = {
  slug: string;
  rowId: string;
  "x-grid-namespace"?: string;
  relateRequest: RelateRequest;
};
export type AddSectionGridTablesSlugSectionsPostApiResponse =
  /** status 201 Successful Response */ SectionOut;
export type AddSectionGridTablesSlugSectionsPostApiArg = {
  slug: string;
  "x-grid-namespace"?: string;
  sectionCreate: SectionCreate;
};
export type ListTypesGridTypesGetApiResponse =
  /** status 200 Successful Response */ TypeDescriptor[];
export type ListTypesGridTypesGetApiArg = void;
export type ValidationError = {
  ctx?: object;
  input?: any;
  loc: (string | number)[];
  msg: string;
  type: string;
};
export type HttpValidationError = {
  detail?: ValidationError[];
};
export type RowOut = {
  id: string;
  payload: {
    [key: string]: any;
  };
};
export type RowPatch = {
  values?: {
    [key: string]: any;
  };
};
export type TableOut = {
  id: string;
  label: string;
  namespace: string;
  natural_key?: string[] | null;
  ownership: string;
  projection_predicate?: {
    [key: string]: any;
  } | null;
  slug: string;
};
export type TableCreate = {
  config?: {
    [key: string]: any;
  };
  label: string;
  natural_key?: string[] | null;
  ownership?: "owned" | "bound";
  projection_predicate?: {
    [key: string]: any;
  } | null;
  slug: string;
};
export type Capabilities = {
  cursor_browsable: boolean;
  default_index_kind?: string | null;
  filter_ops: string[];
  filterable: boolean;
  fuzzy: boolean;
  index_kinds: string[];
  sortable: boolean;
};
export type ColumnOut = {
  capabilities: Capabilities;
  cardinality: string;
  config: {
    [key: string]: any;
  };
  display_order: number;
  id: string;
  is_required: boolean;
  is_unique: boolean;
  key: string;
  label: string;
  materialization: string;
  type_id: string;
};
export type IndexOut = {
  column_keys: string[];
  id: string;
  index_kind: string;
  is_unique: boolean;
  physical_name?: string | null;
  state: string;
};
export type RelationOut = {
  direction: string;
  id: string;
  key: string;
  on_delete: string;
  relation_type: string;
  source_table_id: string;
  target_table_id: string;
  through_table_id?: string | null;
};
export type SectionOut = {
  browse_mode: string;
  id: string;
  is_default: boolean;
  label: string;
  row_filter?: {
    [key: string]: any;
  } | null;
  slug: string;
  sort_spec?:
    | {
        [key: string]: any;
      }[]
    | null;
};
export type TableDescribe = {
  columns: ColumnOut[];
  indexes: IndexOut[];
  relations: RelationOut[];
  sections: SectionOut[];
  table: TableOut;
};
export type ColumnCreate = {
  cardinality?: "one" | "many";
  config?: {
    [key: string]: any;
  };
  default_value?: any;
  display_order?: number;
  is_required?: boolean;
  is_unique?: boolean;
  key: string;
  label: string;
  materialization?: "payload" | "promoted" | "derived";
  relation_key?: string | null;
  type_id: string;
};
export type IndexCreate = {
  column_keys: string[];
  index_kind?: string;
  is_unique?: boolean;
};
export type QueryResult = {
  next_cursor?: string | null;
  rows: RowOut[];
  total?: number | null;
};
export type QueryRequest = {
  cursor?: string | null;
  filter?: {
    [key: string]: any;
  } | null;
  include_total?: boolean;
  limit?: number;
  mode?: "page" | "cursor";
  offset?: number;
  sort?:
    | {
        [key: string]: string;
      }[]
    | null;
};
export type RelationCreate = {
  direction?: "outbound" | "inbound";
  key: string;
  on_delete?: "restrict" | "cascade" | "set_null";
  relation_type: "one_to_one" | "one_to_many" | "many_to_many";
  target_slug: string;
  through_slug?: string | null;
};
export type RowCreate = {
  values?: {
    [key: string]: any;
  };
};
export type RelateRequest = {
  payload?: {
    [key: string]: any;
  };
  relation_key: string;
  target_row_id: string;
};
export type SectionCreate = {
  browse_mode?: "page" | "cursor";
  is_default?: boolean;
  label: string;
  row_filter?: {
    [key: string]: any;
  } | null;
  slug: string;
  sort_spec?:
    | {
        [key: string]: any;
      }[]
    | null;
};
export type TypeDescriptor = {
  capabilities: Capabilities;
  config_schema: {
    [key: string]: any;
  };
  type_id: string;
};
export const {
  useArchiveRowGridRowsRowIdDeleteMutation,
  useGetRowGridRowsRowIdGetQuery,
  useLazyGetRowGridRowsRowIdGetQuery,
  usePatchRowGridRowsRowIdPatchMutation,
  useListTablesGridTablesGetQuery,
  useLazyListTablesGridTablesGetQuery,
  useCreateTableGridTablesPostMutation,
  useDescribeTableGridTablesSlugGetQuery,
  useLazyDescribeTableGridTablesSlugGetQuery,
  useAddColumnGridTablesSlugColumnsPostMutation,
  useAddIndexGridTablesSlugIndexesPostMutation,
  useQueryGridTablesSlugQueryPostMutation,
  useReconcileGridTablesSlugReconcilePostMutation,
  useAddRelationGridTablesSlugRelationsPostMutation,
  useCreateRowGridTablesSlugRowsPostMutation,
  useListLinksGridTablesSlugRowsRowIdLinksGetQuery,
  useLazyListLinksGridTablesSlugRowsRowIdLinksGetQuery,
  useRelateGridTablesSlugRowsRowIdRelatePostMutation,
  useAddSectionGridTablesSlugSectionsPostMutation,
  useListTypesGridTypesGetQuery,
  useLazyListTypesGridTypesGetQuery,
} = injectedRtkApi;
