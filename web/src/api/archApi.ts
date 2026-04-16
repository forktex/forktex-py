import { baseApi as api } from "./baseApi";
export const addTagTypes = ["Architecture"] as const;
const injectedRtkApi = api
  .enhanceEndpoints({
    addTagTypes,
  })
  .injectEndpoints({
    endpoints: (build) => ({
      getArchitectureApiArchitectureGet: build.query<
        GetArchitectureApiArchitectureGetApiResponse,
        GetArchitectureApiArchitectureGetApiArg
      >({
        query: () => ({ url: `/api/architecture` }),
        providesTags: ["Architecture"],
      }),
      getNavigationApiNavigationGet: build.query<
        GetNavigationApiNavigationGetApiResponse,
        GetNavigationApiNavigationGetApiArg
      >({
        query: () => ({ url: `/api/navigation` }),
        providesTags: ["Architecture"],
      }),
      listSystemsApiSystemsGet: build.query<
        ListSystemsApiSystemsGetApiResponse,
        ListSystemsApiSystemsGetApiArg
      >({
        query: () => ({ url: `/api/systems` }),
        providesTags: ["Architecture"],
      }),
      getSystemApiSystemsSystemIdGet: build.query<
        GetSystemApiSystemsSystemIdGetApiResponse,
        GetSystemApiSystemsSystemIdGetApiArg
      >({
        query: (queryArg) => ({ url: `/api/systems/${queryArg.systemId}` }),
        providesTags: ["Architecture"],
      }),
      listEdgesApiEdgesGet: build.query<
        ListEdgesApiEdgesGetApiResponse,
        ListEdgesApiEdgesGetApiArg
      >({
        query: () => ({ url: `/api/edges` }),
        providesTags: ["Architecture"],
      }),
      listPortsApiPortsGet: build.query<
        ListPortsApiPortsGetApiResponse,
        ListPortsApiPortsGetApiArg
      >({
        query: () => ({ url: `/api/ports` }),
        providesTags: ["Architecture"],
      }),
    }),
    overrideExisting: false,
  });
export { injectedRtkApi as archApi };
export type GetArchitectureApiArchitectureGetApiResponse =
  /** status 200 Successful Response */ ArchitectureResponse;
export type GetArchitectureApiArchitectureGetApiArg = void;
export type GetNavigationApiNavigationGetApiResponse =
  /** status 200 Successful Response */ NavigationNode;
export type GetNavigationApiNavigationGetApiArg = void;
export type ListSystemsApiSystemsGetApiResponse =
  /** status 200 Successful Response */ SystemInfo[];
export type ListSystemsApiSystemsGetApiArg = void;
export type GetSystemApiSystemsSystemIdGetApiResponse =
  /** status 200 Successful Response */ SystemInfo;
export type GetSystemApiSystemsSystemIdGetApiArg = {
  systemId: string;
};
export type ListEdgesApiEdgesGetApiResponse =
  /** status 200 Successful Response */ EdgeInfo[];
export type ListEdgesApiEdgesGetApiArg = void;
export type ListPortsApiPortsGetApiResponse =
  /** status 200 Successful Response */ PortAllocation[];
export type ListPortsApiPortsGetApiArg = void;
export type GitInfoModel = {
  branch?: string;
  last_commit?: string;
  message?: string;
  date?: string;
  dirty?: boolean;
  remote?: string;
};
export type PackageInfoModel = {
  name: string;
  path: string;
  version?: string;
  language?: string;
  publishable?: boolean;
  description?: string;
};
export type TechInfo = {
  name: string;
  version?: string | null;
  category?: string;
};
export type PortInfo = {
  host: number;
  container: number;
};
export type ComponentInfo = {
  id: string;
  name: string;
  description: string;
  technology?: string;
  files?: string[];
  line_count?: number;
};
export type ContainerInfo = {
  id: string;
  name: string;
  description: string;
  service_type: string;
  technology?: TechInfo[];
  ports?: PortInfo[];
  image?: string | null;
  health_path?: string | null;
  components?: ComponentInfo[];
};
export type SystemInfo = {
  id: string;
  name: string;
  description: string;
  fsq_level?: string;
  provider?: string | null;
  region?: string | null;
  deploy_strategy?: string | null;
  domains?: string[];
  git?: GitInfoModel | null;
  packages?: PackageInfoModel[];
  containers?: ContainerInfo[];
};
export type EdgeInfo = {
  source: string;
  target: string;
  description: string;
};
export type NavigationNode = {
  id: string;
  name: string;
  type: string;
  level: number;
  data?: {
    [key: string]: any;
  };
  children?: NavigationNode[];
};
export type ArchitectureResponse = {
  generated_at: string;
  name: string;
  description: string;
  systems: SystemInfo[];
  relationships?: EdgeInfo[];
  navigation: NavigationNode;
};
export type ValidationError = {
  loc: (string | number)[];
  msg: string;
  type: string;
  input?: any;
  ctx?: object;
};
export type HttpValidationError = {
  detail?: ValidationError[];
};
export type PortAllocation = {
  system: string;
  service: string;
  host_port: number;
  container_port: number;
  type: string;
};
export const {
  useGetArchitectureApiArchitectureGetQuery,
  useGetNavigationApiNavigationGetQuery,
  useListSystemsApiSystemsGetQuery,
  useGetSystemApiSystemsSystemIdGetQuery,
  useListEdgesApiEdgesGetQuery,
  useListPortsApiPortsGetQuery,
} = injectedRtkApi;
