import { MessageDefinitionField } from "@foxglove/message-definition";

import { AnyAnnotation } from "./astTypes";

/** Final resolved MessageDefinition types */

/** Higher-level resolved definitions (struct, modules)*/
export type IDLMessageDefinition =
  | IDLStructDefinition
  | IDLModuleDefinition
  | IDLUnionDefinition;

export class IDLAggregatedDefinition {
  public name: string;
  public declare annotations?: Record<string, AnyAnnotation>;
  constructor(name: string, annotations?: Record<string, AnyAnnotation>) {
    this.name = name;
    if (annotations !== undefined) {
      this.annotations = annotations;
    }
  }
}

export class IDLModuleDefinition extends IDLAggregatedDefinition {
  /** Should only contain constants directly contained within module.
   * Does not include constants contained within submodules any other definitions contained within the module.
   */
  constructor(
    name: string,
    public definitions: IDLMessageDefinitionField[],
    annotations?: Record<string, AnyAnnotation>,
  ) {
    super(name, annotations);
  }
}

export class IDLStructDefinition extends IDLAggregatedDefinition {
  constructor(
    name: string,
    public definitions: IDLMessageDefinitionField[],
    annotations?: Record<string, AnyAnnotation>,
  ) {
    super(name, annotations);
  }
}

export class IDLUnionDefinition extends IDLAggregatedDefinition {
  public switchType: string;
  public cases: Case[];
  public declare defaultCase?: IDLMessageDefinitionField;
  /** Type to read that determines what case to use. Must be numeric or boolean */
  constructor(
    name: string,
    switchType: string,
    cases: Case[],
    /** Resolved default type specification */
    defaultCase?: IDLMessageDefinitionField,
    annotations?: Record<string, AnyAnnotation>,
  ) {
    super(name, annotations);
    this.switchType = switchType;
    this.cases = cases;
    if (defaultCase !== undefined) {
      this.defaultCase = defaultCase;
    }
  }
}

/** Case with resolved predicates and type definition */
export type Case = {
  /** Array of values that, if read, would cause the type to be used */
  predicates: (number | boolean)[];
  /** Type to be used if value from predicate array is read */
  type: IDLMessageDefinitionField;
};

/**
 * All primitive struct-members are resolved such that they do not contain references to typedefs or constant values.
 * The only references they hold are to complex values (structs, unions ).
 */
export type IDLMessageDefinitionField = Omit<MessageDefinitionField, "arrayLength"> & {
  /** Annotations from schema. Only default annotations are resolved currently */
  annotations?: Record<string, AnyAnnotation>;
  /** Length of array(s). Outermost arrays are first */
  arrayLengths?: number[];
};
