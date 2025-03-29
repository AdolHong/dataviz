// 可视化接口
export interface Artifact {
  id: string; // 自动生成
  title: string;
  description?: string;
  code: string;
  dependencies: string[]; // 依赖哪个数据源
  executor_engine: string;
  ArtifactParams?: ArtifactParam[];
}

// 可视化参数接口
export interface ArtifactParam {
  id: string; // 自动生成
  name: string;
  alias?: string; // 参数可以有别名, 一般是中文，便于理解参数
  description?: string;
  valueType: 'string' | 'double' | 'boolean' | 'int';
  paramType:
    | PlainSingleArtifactParamType
    | PlainMultipleArtifactParamType
    | CascadeSingleArtifactParamType
    | CascadeMultipleArtifactParamType;
}

export interface PlainSingleArtifactParamType {
  type: 'plain_single';
  default: string;
  choices: string[];
}

export interface PlainMultipleArtifactParamType {
  type: 'plain_multiple';
  default: string[];
  choices: string[];
  dfAlias: string;
  dfColumn: string;
}

export interface CascadeSingleArtifactParamType {
  type: 'cascade_single';
  default: string;
  choices: string[];
  dfAlias: string;
  dfColumn: string;
  level: number;
}

export interface CascadeMultipleArtifactParamType {
  type: 'cascade_multiple';
  default: string[];
  choices: string[];
  dfAlias: string;
  dfColumn: string;
  level: number;
}
