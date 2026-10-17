use pyo3::exceptions::{PyKeyError, PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::{PyBool, PyBytes, PyDict, PyFloat, PyInt, PyList, PyString};
use pyo3::IntoPyObjectExt;
use serde::de::{self, MapAccess, SeqAccess, Visitor};
use serde::ser::SerializeMap;
use serde::{Deserialize, Deserializer, Serialize};
use serde_json::{Map, Number, Value};
use std::borrow::Cow;
use std::cmp::{Ordering, Reverse};
use std::collections::{BTreeMap, BTreeSet, BinaryHeap, HashMap, HashSet, VecDeque};
use std::fmt;
use std::mem::size_of;
use std::sync::{Arc, RwLock};

type Id = u32;
type EngineResult<T> = Result<T, EngineError>;
type PythonFilters = Vec<(String, String, Py<PyAny>)>;
type BfsArrays = (Vec<Id>, Vec<Option<Id>>, Vec<usize>, Vec<Option<Id>>);
const ID_LIMIT: u64 = u32::MAX as u64 + 1;
const SNAPSHOT_VERSION: u32 = 1;
const MAX_PROPERTY_DEPTH: usize = 64;

// Small property vectors avoid a full B-tree node allocation for every sparse edge.
#[derive(Clone, Debug, Default, PartialEq)]
struct Properties {
    values: Vec<(Arc<str>, Value)>,
}

impl Properties {
    #[cfg(test)]
    fn new() -> Self {
        Self::default()
    }

    fn get(&self, key: &str) -> Option<&Value> {
        self.values
            .binary_search_by(|(name, _)| name.as_ref().cmp(key))
            .ok()
            .map(|position| &self.values[position].1)
    }

    fn values(&self) -> impl Iterator<Item = &Value> {
        self.values.iter().map(|(_, value)| value)
    }

    fn intern_keys(&mut self, pool: &mut HashSet<Arc<str>>) {
        for (key, _) in &mut self.values {
            if let Some(interned) = pool.get(key.as_ref()) {
                *key = Arc::clone(interned);
            } else {
                pool.insert(Arc::clone(key));
            }
        }
    }
}

impl From<Map<String, Value>> for Properties {
    fn from(values: Map<String, Value>) -> Self {
        Self {
            values: values
                .into_iter()
                .map(|(key, value)| (Arc::from(key), value))
                .collect(),
        }
    }
}

impl<'a> IntoIterator for &'a Properties {
    type Item = &'a (Arc<str>, Value);
    type IntoIter = std::slice::Iter<'a, (Arc<str>, Value)>;

    fn into_iter(self) -> Self::IntoIter {
        self.values.iter()
    }
}

impl Serialize for Properties {
    fn serialize<S: serde::Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let mut map = serializer.serialize_map(Some(self.values.len()))?;
        for (key, value) in &self.values {
            map.serialize_entry(key.as_ref(), value)?;
        }
        map.end()
    }
}

#[derive(Debug)]
enum EngineError {
    Missing(String),
    Invalid(String),
    State(String),
}

impl fmt::Display for EngineError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Missing(message) | Self::Invalid(message) | Self::State(message) => {
                formatter.write_str(message)
            }
        }
    }
}

impl From<EngineError> for PyErr {
    fn from(error: EngineError) -> Self {
        match error {
            EngineError::Missing(message) => PyKeyError::new_err(message),
            EngineError::Invalid(message) => PyValueError::new_err(message),
            EngineError::State(message) => PyRuntimeError::new_err(message),
        }
    }
}

fn invalid(message: impl Into<String>) -> EngineError {
    EngineError::Invalid(message.into())
}

fn validate_value(value: &Value, depth: usize) -> EngineResult<()> {
    if depth > MAX_PROPERTY_DEPTH {
        return Err(invalid("property nesting exceeds 64 levels"));
    }
    match value {
        Value::Number(number) => {
            if number.is_f64() {
                if !number.as_f64().is_some_and(f64::is_finite) {
                    return Err(invalid("property floats must be finite"));
                }
            } else if number.as_i64().is_none() {
                return Err(invalid("property integers must fit signed 64 bits"));
            }
        }
        Value::Array(values) => {
            for value in values {
                validate_value(value, depth + 1)?;
            }
        }
        Value::Object(values) => {
            for value in values.values() {
                validate_value(value, depth + 1)?;
            }
        }
        _ => {}
    }
    Ok(())
}

fn validate_properties(properties: &Properties) -> EngineResult<()> {
    for value in properties.values() {
        validate_value(value, 1)?;
    }
    Ok(())
}

fn properties_from_python(value: &Bound<'_, PyAny>) -> PyResult<Properties> {
    let dict = value
        .cast::<PyDict>()
        .map_err(|_| PyValueError::new_err("properties must be a dict with string keys"))?;
    let mut active = HashSet::from([value.as_ptr() as usize]);
    let mut values = Vec::with_capacity(dict.len());
    for (key, item) in dict.iter() {
        if !key.is_instance_of::<PyString>() {
            return Err(PyValueError::new_err("property dict keys must be strings"));
        }
        values.push((
            Arc::<str>::from(key.extract::<String>()?),
            value_from_python(&item, 1, &mut active)?,
        ));
    }
    values.sort_unstable_by(|(left, _), (right, _)| left.cmp(right));
    Ok(Properties { values })
}

fn value_from_python(
    value: &Bound<'_, PyAny>,
    depth: usize,
    active: &mut HashSet<usize>,
) -> PyResult<Value> {
    if depth > MAX_PROPERTY_DEPTH {
        return Err(PyValueError::new_err("property nesting exceeds 64 levels"));
    }
    if value.is_none() {
        return Ok(Value::Null);
    }
    if value.is_instance_of::<PyBool>() {
        return Ok(Value::Bool(value.extract()?));
    }
    if value.is_instance_of::<PyInt>() {
        let integer = value
            .extract::<i64>()
            .map_err(|_| PyValueError::new_err("property integers must fit signed 64 bits"))?;
        return Ok(Value::Number(integer.into()));
    }
    if value.is_instance_of::<PyFloat>() {
        let float = value.extract::<f64>()?;
        return Number::from_f64(float)
            .map(Value::Number)
            .ok_or_else(|| PyValueError::new_err("property floats must be finite"));
    }
    if value.is_instance_of::<PyString>() {
        return Ok(Value::String(value.extract()?));
    }
    let address = value.as_ptr() as usize;
    if !active.insert(address) {
        return Err(PyValueError::new_err(
            "cyclic properties are not JSON values",
        ));
    }
    let result = if let Ok(list) = value.cast::<PyList>() {
        let mut values = Vec::with_capacity(list.len());
        for item in list.iter() {
            values.push(value_from_python(&item, depth + 1, active)?);
        }
        Ok(Value::Array(values))
    } else if let Ok(dict) = value.cast::<PyDict>() {
        let mut values = Map::new();
        for (key, item) in dict.iter() {
            if !key.is_instance_of::<PyString>() {
                return Err(PyValueError::new_err("property dict keys must be strings"));
            }
            values.insert(key.extract()?, value_from_python(&item, depth + 1, active)?);
        }
        Ok(Value::Object(values))
    } else {
        Err(PyValueError::new_err(
            "supported properties are null, bool, signed64 int, finite float, str, list and dict",
        ))
    };
    active.remove(&address);
    result
}

fn value_to_python<'py>(py: Python<'py>, value: &Value) -> PyResult<Bound<'py, PyAny>> {
    match value {
        Value::Null => Ok(py.None().into_bound(py)),
        Value::Bool(value) => value.into_bound_py_any(py),
        Value::Number(value) => {
            if let Some(integer) = value.as_i64() {
                integer.into_bound_py_any(py)
            } else {
                value.as_f64().unwrap().into_bound_py_any(py)
            }
        }
        Value::String(value) => value.into_bound_py_any(py),
        Value::Array(values) => {
            let list = PyList::empty(py);
            for value in values {
                list.append(value_to_python(py, value)?)?;
            }
            Ok(list.into_any())
        }
        Value::Object(properties) => {
            let dict = PyDict::new(py);
            for (key, value) in properties {
                dict.set_item(key, value_to_python(py, value)?)?;
            }
            Ok(dict.into_any())
        }
    }
}

fn properties_to_python<'py>(
    py: Python<'py>,
    properties: &Properties,
) -> PyResult<Bound<'py, PyDict>> {
    let dict = PyDict::new(py);
    for (key, value) in properties {
        dict.set_item(key.as_ref(), value_to_python(py, value)?)?;
    }
    Ok(dict)
}

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
enum IndexKey {
    Null,
    Bool(bool),
    Int(i64),
    Float(u64),
    String(String),
    Array(Vec<IndexKey>),
    Object(Vec<(String, IndexKey)>),
}

impl IndexKey {
    fn new(value: &Value) -> Self {
        match value {
            Value::Null => Self::Null,
            Value::Bool(value) => Self::Bool(*value),
            Value::Number(value) => {
                if let Some(integer) = value.as_i64() {
                    Self::Int(integer)
                } else {
                    let float = value.as_f64().unwrap();
                    Self::Float(if float == 0.0 { 0 } else { float.to_bits() })
                }
            }
            Value::String(value) => Self::String(value.clone()),
            Value::Array(values) => Self::Array(values.iter().map(Self::new).collect()),
            Value::Object(values) => Self::Object(
                values
                    .iter()
                    .map(|(key, value)| (key.clone(), Self::new(value)))
                    .collect(),
            ),
        }
    }

    fn heap_bytes(&self) -> usize {
        match self {
            Self::String(value) => value.capacity(),
            Self::Array(values) => {
                values.capacity() * size_of::<Self>()
                    + values.iter().map(Self::heap_bytes).sum::<usize>()
            }
            Self::Object(values) => {
                values.capacity() * size_of::<(String, Self)>()
                    + values
                        .iter()
                        .map(|(key, value)| key.capacity() + value.heap_bytes())
                        .sum::<usize>()
            }
            _ => 0,
        }
    }
}

#[derive(Clone, Default)]
struct EqualityIndex {
    postings: HashMap<IndexKey, BTreeSet<Id>>,
}

impl EqualityIndex {
    fn add(&mut self, node: Id, value: &Value) {
        self.postings
            .entry(IndexKey::new(value))
            .or_default()
            .insert(node);
    }

    fn remove(&mut self, node: Id, value: &Value) {
        let key = IndexKey::new(value);
        if let Some(posting) = self.postings.get_mut(&key) {
            posting.remove(&node);
            if posting.is_empty() {
                self.postings.remove(&key);
            }
        }
    }
}

#[derive(Clone)]
struct Node {
    id: Id,
    scope: Id,
    local_id: String,
    child_scope: Option<Id>,
    attrs: Properties,
    outgoing: Vec<Id>,
    incoming: Vec<Id>,
}

#[derive(Clone)]
struct Edge {
    id: Id,
    src: Id,
    dst: Id,
    rel: Id,
    attrs: Properties,
    out_pos: usize,
    in_pos: usize,
    rel_pos: usize,
    scope_pos: usize,
}

#[derive(Clone, Default)]
struct Scope {
    owner: Option<Id>,
    names: HashMap<String, Id>,
    members: BTreeSet<Id>,
    edges: Vec<Id>,
    indexes: HashMap<String, EqualityIndex>,
}

#[derive(Clone)]
struct Relation {
    name: String,
    edges: Vec<Id>,
}

#[derive(Clone)]
struct Store {
    revision: u64,
    next_node_id: u64,
    next_edge_id: u64,
    next_scope_id: u64,
    nodes: Vec<Node>,
    node_positions: HashMap<Id, usize>,
    edges: Vec<Edge>,
    edge_positions: HashMap<Id, usize>,
    edge_keys: HashMap<(Id, Id, Id), Id>,
    scopes: HashMap<Id, Scope>,
    relations: Vec<Relation>,
    relation_ids: HashMap<String, Id>,
    property_keys: HashSet<Arc<str>>,
}

impl Default for Store {
    fn default() -> Self {
        Self {
            revision: 0,
            next_node_id: 0,
            next_edge_id: 0,
            next_scope_id: 1,
            nodes: Vec::new(),
            node_positions: HashMap::new(),
            edges: Vec::new(),
            edge_positions: HashMap::new(),
            edge_keys: HashMap::new(),
            scopes: HashMap::from([(0, Scope::default())]),
            relations: Vec::new(),
            relation_ids: HashMap::new(),
            property_keys: HashSet::new(),
        }
    }
}

#[derive(Clone, Copy)]
enum Direction {
    Out,
    In,
    Both,
}

impl Direction {
    fn parse(direction: &str) -> EngineResult<Self> {
        match direction {
            "out" => Ok(Self::Out),
            "in" => Ok(Self::In),
            "both" => Ok(Self::Both),
            _ => Err(invalid("direction must be 'out', 'in' or 'both'")),
        }
    }
}

#[derive(Clone, Copy)]
enum RelationFilter {
    Any,
    Exact(Id),
    Missing,
}

impl RelationFilter {
    fn matches(self, relation: Id) -> bool {
        match self {
            Self::Any => true,
            Self::Exact(expected) => relation == expected,
            Self::Missing => false,
        }
    }
}

#[derive(Clone, Copy)]
enum Operator {
    Eq,
    Ne,
    Gt,
    Gte,
    Lt,
    Lte,
    In,
    Contains,
    Exists,
    StartsWith,
}

struct Filter {
    key: String,
    op: Operator,
    value: Value,
}

impl Filter {
    fn new(key: String, op: &str, value: Value) -> EngineResult<Self> {
        validate_value(&value, 0)?;
        let op = match op {
            "eq" => Operator::Eq,
            "ne" => Operator::Ne,
            "gt" => Operator::Gt,
            "gte" => Operator::Gte,
            "lt" => Operator::Lt,
            "lte" => Operator::Lte,
            "in" => {
                if !value.is_array() {
                    return Err(invalid("the 'in' operator requires a list"));
                }
                Operator::In
            }
            "contains" => Operator::Contains,
            "exists" => {
                if !value.is_boolean() {
                    return Err(invalid("the 'exists' operator requires a bool"));
                }
                Operator::Exists
            }
            "startswith" => {
                if !value.is_string() {
                    return Err(invalid("the 'startswith' operator requires a string"));
                }
                Operator::StartsWith
            }
            _ => return Err(invalid(format!("unknown property operator: {op}"))),
        };
        Ok(Self { key, op, value })
    }

    fn matches(&self, properties: &Properties) -> bool {
        let actual = properties.get(&self.key);
        if matches!(self.op, Operator::Exists) {
            return actual.is_some() == self.value.as_bool().unwrap();
        }
        let Some(actual) = actual else {
            return false;
        };
        match self.op {
            Operator::Eq => actual == &self.value,
            Operator::Ne => actual != &self.value,
            Operator::Gt => compare_values(actual, &self.value) == Some(Ordering::Greater),
            Operator::Gte => matches!(
                compare_values(actual, &self.value),
                Some(Ordering::Greater | Ordering::Equal)
            ),
            Operator::Lt => compare_values(actual, &self.value) == Some(Ordering::Less),
            Operator::Lte => matches!(
                compare_values(actual, &self.value),
                Some(Ordering::Less | Ordering::Equal)
            ),
            Operator::In => self
                .value
                .as_array()
                .unwrap()
                .iter()
                .any(|value| value == actual),
            Operator::Contains => match actual {
                Value::Array(values) => values.iter().any(|value| value == &self.value),
                Value::Object(values) => self
                    .value
                    .as_str()
                    .is_some_and(|key| values.contains_key(key)),
                Value::String(value) => {
                    self.value.as_str().is_some_and(|part| value.contains(part))
                }
                _ => false,
            },
            Operator::StartsWith => actual
                .as_str()
                .is_some_and(|value| value.starts_with(self.value.as_str().unwrap())),
            Operator::Exists => unreachable!(),
        }
    }
}

// Compare mixed numeric types without rounding an i64 through f64 (notably above 2^53).
fn compare_int_float(integer: i64, float: f64) -> Ordering {
    if float >= 9_223_372_036_854_775_808.0 {
        return Ordering::Less;
    }
    if float < -9_223_372_036_854_775_808.0 {
        return Ordering::Greater;
    }
    let truncated = float as i64;
    match integer.cmp(&truncated) {
        Ordering::Equal if float.fract() > 0.0 => Ordering::Less,
        Ordering::Equal if float.fract() < 0.0 => Ordering::Greater,
        other => other,
    }
}

fn compare_values(left: &Value, right: &Value) -> Option<Ordering> {
    match (left, right) {
        (Value::Number(left), Value::Number(right)) => match (left.as_i64(), right.as_i64()) {
            (Some(left), Some(right)) => Some(left.cmp(&right)),
            (Some(left), None) => Some(compare_int_float(left, right.as_f64().unwrap())),
            (None, Some(right)) => Some(compare_int_float(right, left.as_f64().unwrap()).reverse()),
            (None, None) => left.as_f64().unwrap().partial_cmp(&right.as_f64().unwrap()),
        },
        (Value::String(left), Value::String(right)) => Some(left.cmp(right)),
        _ => None,
    }
}

fn filters_from_python(py: Python<'_>, filters: PythonFilters) -> PyResult<Vec<Filter>> {
    filters
        .into_iter()
        .map(|(key, op, value)| {
            let value = value_from_python(value.bind(py), 0, &mut HashSet::new())?;
            Filter::new(key, &op, value).map_err(Into::into)
        })
        .collect()
}

impl Store {
    fn scope(&self, scope: Id) -> EngineResult<&Scope> {
        self.scopes
            .get(&scope)
            .ok_or_else(|| EngineError::Missing(format!("scope {scope}")))
    }

    fn node(&self, node: Id) -> EngineResult<&Node> {
        self.node_positions
            .get(&node)
            .map(|&position| &self.nodes[position])
            .ok_or_else(|| EngineError::Missing(format!("node {node}")))
    }

    fn node_mut(&mut self, node: Id) -> &mut Node {
        &mut self.nodes[self.node_positions[&node]]
    }

    fn edge(&self, edge: Id) -> EngineResult<&Edge> {
        self.edge_positions
            .get(&edge)
            .map(|&position| &self.edges[position])
            .ok_or_else(|| EngineError::Missing(format!("edge {edge}")))
    }

    fn edge_mut(&mut self, edge: Id) -> &mut Edge {
        &mut self.edges[self.edge_positions[&edge]]
    }

    fn check_revision(&self) -> EngineResult<()> {
        if self.revision == u64::MAX {
            Err(invalid("revision counter exhausted"))
        } else {
            Ok(())
        }
    }

    fn check_ids(next: u64, count: usize, kind: &str) -> EngineResult<()> {
        if next
            .checked_add(count as u64)
            .is_none_or(|end| end > ID_LIMIT)
        {
            Err(invalid(format!("{kind} ID space exhausted")))
        } else {
            Ok(())
        }
    }

    fn selected_scopes(&self, scope: Id, recursive: bool) -> EngineResult<Vec<Id>> {
        self.scope(scope)?;
        let mut selected = vec![scope];
        if recursive {
            let mut cursor = 0;
            while cursor < selected.len() {
                for node in &self.scopes[&selected[cursor]].members {
                    if let Some(child) = self.node(*node)?.child_scope {
                        selected.push(child);
                    }
                }
                cursor += 1;
            }
        }
        Ok(selected)
    }

    fn node_ids(&self, scope: Id, recursive: bool) -> EngineResult<Vec<Id>> {
        let scopes = self.selected_scopes(scope, recursive)?;
        let mut nodes: Vec<_> = scopes
            .iter()
            .flat_map(|scope| self.scopes[scope].members.iter().copied())
            .collect();
        nodes.sort_unstable();
        Ok(nodes)
    }

    fn create_scope(&mut self, owner: Id) -> EngineResult<Id> {
        if let Some(scope) = self.node(owner)?.child_scope {
            return Ok(scope);
        }
        Self::check_ids(self.next_scope_id, 1, "scope")?;
        self.check_revision()?;
        let id = self.next_scope_id as Id;
        self.next_scope_id += 1;
        self.scopes.insert(
            id,
            Scope {
                owner: Some(owner),
                ..Scope::default()
            },
        );
        self.node_mut(owner).child_scope = Some(id);
        self.revision += 1;
        Ok(id)
    }

    fn add_nodes(&mut self, scope: Id, nodes: Vec<(String, Properties)>) -> EngineResult<Vec<Id>> {
        let target = self.scope(scope)?;
        let mut new_names = HashSet::new();
        for (name, attrs) in &nodes {
            validate_properties(attrs)?;
            if !target.names.contains_key(name) {
                new_names.insert(name.as_str());
            }
        }
        Self::check_ids(self.next_node_id, new_names.len(), "node")?;
        if nodes.is_empty() {
            return Ok(Vec::new());
        }
        self.check_revision()?;
        let mut ids = Vec::with_capacity(nodes.len());
        for (local_id, mut attrs) in nodes {
            attrs.intern_keys(&mut self.property_keys);
            let id = if let Some(&id) = self.scopes[&scope].names.get(&local_id) {
                let old_attrs = std::mem::replace(&mut self.node_mut(id).attrs, attrs);
                let attrs = &self.nodes[self.node_positions[&id]].attrs;
                for (property, index) in &mut self.scopes.get_mut(&scope).unwrap().indexes {
                    if let Some(value) = old_attrs.get(property) {
                        index.remove(id, value);
                    }
                    if let Some(value) = attrs.get(property) {
                        index.add(id, value);
                    }
                }
                id
            } else {
                let id = self.next_node_id as Id;
                self.next_node_id += 1;
                self.node_positions.insert(id, self.nodes.len());
                let target = self.scopes.get_mut(&scope).unwrap();
                target.names.insert(local_id.clone(), id);
                target.members.insert(id);
                for (property, index) in &mut target.indexes {
                    if let Some(value) = attrs.get(property) {
                        index.add(id, value);
                    }
                }
                self.nodes.push(Node {
                    id,
                    scope,
                    local_id,
                    child_scope: None,
                    attrs,
                    outgoing: Vec::new(),
                    incoming: Vec::new(),
                });
                id
            };
            ids.push(id);
        }
        self.revision += 1;
        Ok(ids)
    }

    fn intern_relation(&mut self, relation: &str) -> Id {
        if let Some(&id) = self.relation_ids.get(relation) {
            return id;
        }
        let id = self.relations.len() as Id;
        self.relations.push(Relation {
            name: relation.to_owned(),
            edges: Vec::new(),
        });
        self.relation_ids.insert(relation.to_owned(), id);
        id
    }

    fn insert_edge(&mut self, id: Id, src: Id, dst: Id, rel: Id, attrs: Properties) {
        let scope = self.nodes[self.node_positions[&src]].scope;
        let out_pos = self.node_mut(src).outgoing.len();
        self.node_mut(src).outgoing.push(id);
        let in_pos = self.node_mut(dst).incoming.len();
        self.node_mut(dst).incoming.push(id);
        let rel_pos = self.relations[rel as usize].edges.len();
        self.relations[rel as usize].edges.push(id);
        let source_scope = self.scopes.get_mut(&scope).unwrap();
        let scope_pos = source_scope.edges.len();
        source_scope.edges.push(id);
        self.edge_keys.insert((src, dst, rel), id);
        self.edge_positions.insert(id, self.edges.len());
        self.edges.push(Edge {
            id,
            src,
            dst,
            rel,
            attrs,
            out_pos,
            in_pos,
            rel_pos,
            scope_pos,
        });
    }

    fn add_edges(&mut self, edges: Vec<(Id, Id, String, Properties)>) -> EngineResult<Vec<Id>> {
        let mut new_keys = HashSet::new();
        let mut new_relations = HashSet::new();
        for (src, dst, rel, attrs) in &edges {
            self.node(*src)?;
            self.node(*dst)?;
            validate_properties(attrs)?;
            let existing = self
                .relation_ids
                .get(rel)
                .and_then(|&relation| self.edge_keys.get(&(*src, *dst, relation)));
            if existing.is_none() {
                new_keys.insert((*src, *dst, rel.as_str()));
            }
            if !self.relation_ids.contains_key(rel) {
                new_relations.insert(rel.as_str());
            }
        }
        Self::check_ids(self.next_edge_id, new_keys.len(), "edge")?;
        Self::check_ids(self.relations.len() as u64, new_relations.len(), "relation")?;
        if edges.is_empty() {
            return Ok(Vec::new());
        }
        self.check_revision()?;
        let mut ids = Vec::with_capacity(edges.len());
        for (src, dst, relation, mut attrs) in edges {
            attrs.intern_keys(&mut self.property_keys);
            let rel = self.intern_relation(&relation);
            let id = if let Some(&id) = self.edge_keys.get(&(src, dst, rel)) {
                self.edge_mut(id).attrs = attrs;
                id
            } else {
                let id = self.next_edge_id as Id;
                self.next_edge_id += 1;
                self.insert_edge(id, src, dst, rel, attrs);
                id
            };
            ids.push(id);
        }
        self.revision += 1;
        Ok(ids)
    }

    fn add_edges_local(
        &mut self,
        scope: Id,
        edges: Vec<(String, String, String, Properties)>,
    ) -> EngineResult<Vec<Id>> {
        let target = self.scope(scope)?;
        let mut prepared = Vec::with_capacity(edges.len());
        for (src, dst, rel, attrs) in edges {
            let src =
                target.names.get(&src).copied().ok_or_else(|| {
                    EngineError::Missing(format!("node {src:?} in scope {scope}"))
                })?;
            let dst =
                target.names.get(&dst).copied().ok_or_else(|| {
                    EngineError::Missing(format!("node {dst:?} in scope {scope}"))
                })?;
            prepared.push((src, dst, rel, attrs));
        }
        self.add_edges(prepared)
    }

    fn remove_edge(&mut self, id: Id) -> bool {
        let Some(position) = self.edge_positions.remove(&id) else {
            return false;
        };
        let edge = self.edges.swap_remove(position);
        if let Some(moved) = self.edges.get(position) {
            self.edge_positions.insert(moved.id, position);
        }
        self.edge_keys.remove(&(edge.src, edge.dst, edge.rel));
        let outgoing = &mut self.node_mut(edge.src).outgoing;
        outgoing.swap_remove(edge.out_pos);
        if let Some(&moved) = outgoing.get(edge.out_pos) {
            self.edge_mut(moved).out_pos = edge.out_pos;
        }
        let incoming = &mut self.node_mut(edge.dst).incoming;
        incoming.swap_remove(edge.in_pos);
        if let Some(&moved) = incoming.get(edge.in_pos) {
            self.edge_mut(moved).in_pos = edge.in_pos;
        }
        let relations = &mut self.relations[edge.rel as usize].edges;
        relations.swap_remove(edge.rel_pos);
        if let Some(&moved) = relations.get(edge.rel_pos) {
            self.edge_mut(moved).rel_pos = edge.rel_pos;
        }
        let scope = self.nodes[self.node_positions[&edge.src]].scope;
        let source_edges = &mut self.scopes.get_mut(&scope).unwrap().edges;
        source_edges.swap_remove(edge.scope_pos);
        if let Some(&moved) = source_edges.get(edge.scope_pos) {
            self.edge_mut(moved).scope_pos = edge.scope_pos;
        }
        true
    }

    fn remove_edges(&mut self, edges: Vec<Id>) -> EngineResult<usize> {
        if edges
            .iter()
            .any(|edge| self.edge_positions.contains_key(edge))
        {
            self.check_revision()?;
        }
        let mut removed = 0;
        for edge in edges {
            removed += usize::from(self.remove_edge(edge));
        }
        if removed > 0 {
            self.revision += 1;
        }
        Ok(removed)
    }

    fn remove_node_record(&mut self, id: Id) {
        while let Some(&edge) = self.node_mut(id).outgoing.last() {
            self.remove_edge(edge);
        }
        while let Some(&edge) = self.node_mut(id).incoming.last() {
            self.remove_edge(edge);
        }
        let position = self.node_positions.remove(&id).unwrap();
        let node = self.nodes.swap_remove(position);
        if let Some(moved) = self.nodes.get(position) {
            self.node_positions.insert(moved.id, position);
        }
        let scope = self.scopes.get_mut(&node.scope).unwrap();
        scope.members.remove(&id);
        scope.names.remove(&node.local_id);
        for (property, index) in &mut scope.indexes {
            if let Some(value) = node.attrs.get(property) {
                index.remove(id, value);
            }
        }
    }

    fn clear_scope(&mut self, scope: Id) -> EngineResult<()> {
        let scopes = self.selected_scopes(scope, true)?;
        let nodes: Vec<_> = scopes
            .iter()
            .flat_map(|scope| self.scopes[scope].members.iter().copied())
            .collect();
        if nodes.is_empty() && scopes.len() == 1 {
            return Ok(());
        }
        self.check_revision()?;
        for node in nodes {
            self.remove_node_record(node);
        }
        for child in scopes.into_iter().skip(1) {
            self.scopes.remove(&child);
        }
        self.revision += 1;
        Ok(())
    }

    fn remove_node(&mut self, node: Id) -> EngineResult<bool> {
        let Some(&position) = self.node_positions.get(&node) else {
            return Ok(false);
        };
        let scopes = match self.nodes[position].child_scope {
            Some(scope) => self.selected_scopes(scope, true)?,
            None => Vec::new(),
        };
        self.check_revision()?;
        let nodes: Vec<_> = scopes
            .iter()
            .flat_map(|scope| self.scopes[scope].members.iter().copied())
            .collect();
        for child in nodes {
            self.remove_node_record(child);
        }
        self.remove_node_record(node);
        for scope in scopes {
            self.scopes.remove(&scope);
        }
        self.revision += 1;
        Ok(true)
    }

    fn relation_filter(&self, rel: Option<&str>) -> RelationFilter {
        match rel {
            None => RelationFilter::Any,
            Some(rel) => self
                .relation_ids
                .get(rel)
                .copied()
                .map(RelationFilter::Exact)
                .unwrap_or(RelationFilter::Missing),
        }
    }

    fn edge_local_id(
        &self,
        scope: Id,
        src: &str,
        dst: &str,
        rel: &str,
    ) -> EngineResult<Option<Id>> {
        let scope = self.scope(scope)?;
        Ok(scope
            .names
            .get(src)
            .zip(scope.names.get(dst))
            .and_then(|(&src, &dst)| {
                self.relation_ids
                    .get(rel)
                    .and_then(|&rel| self.edge_keys.get(&(src, dst, rel)))
                    .copied()
            }))
    }

    fn edge_ids(
        &self,
        scope: Id,
        recursive: bool,
        src: Option<Id>,
        dst: Option<Id>,
        rel: Option<&str>,
        filters: &[Filter],
    ) -> EngineResult<Vec<Id>> {
        let selected = self.selected_scopes(scope, recursive)?;
        let scopes: HashSet<_> = selected.iter().copied().collect();
        let relation = self.relation_filter(rel);
        if matches!(relation, RelationFilter::Missing) {
            return Ok(Vec::new());
        }
        let mut candidates: Option<&[Id]> = if !recursive {
            Some(&self.scopes[&scope].edges)
        } else {
            None
        };
        if let Some(src) = src {
            let Ok(node) = self.node(src) else {
                return Ok(Vec::new());
            };
            if candidates.is_none_or(|edges| node.outgoing.len() < edges.len()) {
                candidates = Some(&node.outgoing);
            }
        }
        if let Some(dst) = dst {
            let Ok(node) = self.node(dst) else {
                return Ok(Vec::new());
            };
            if candidates.is_none_or(|edges| node.incoming.len() < edges.len()) {
                candidates = Some(&node.incoming);
            }
        }
        if let RelationFilter::Exact(rel) = relation {
            let edges = &self.relations[rel as usize].edges;
            if candidates.is_none_or(|selected| edges.len() < selected.len()) {
                candidates = Some(edges);
            }
        }
        let mut result = Vec::new();
        let mut visit = |id: Id| {
            let edge = &self.edges[self.edge_positions[&id]];
            if scopes.contains(&self.nodes[self.node_positions[&edge.src]].scope)
                && src.is_none_or(|src| src == edge.src)
                && dst.is_none_or(|dst| dst == edge.dst)
                && relation.matches(edge.rel)
                && filters.iter().all(|filter| filter.matches(&edge.attrs))
            {
                result.push(id);
            }
        };
        if let Some(candidates) = candidates {
            for &id in candidates {
                visit(id);
            }
        } else {
            for scope in selected {
                for &id in &self.scopes[&scope].edges {
                    visit(id);
                }
            }
        }
        result.sort_unstable();
        Ok(result)
    }

    fn regular_arcs(&self, node: Id, direction: Direction, rel: RelationFilter) -> Vec<(Id, Id)> {
        let node = &self.nodes[self.node_positions[&node]];
        let mut arcs = Vec::new();
        if !matches!(direction, Direction::In) {
            for &edge in &node.outgoing {
                let edge = &self.edges[self.edge_positions[&edge]];
                if rel.matches(edge.rel) {
                    arcs.push((edge.dst, edge.id));
                }
            }
        }
        if !matches!(direction, Direction::Out) {
            for &edge in &node.incoming {
                let edge = &self.edges[self.edge_positions[&edge]];
                if rel.matches(edge.rel)
                    && (!matches!(direction, Direction::Both) || edge.src != node.id)
                {
                    arcs.push((edge.src, edge.id));
                }
            }
        }
        arcs
    }

    fn neighbors(
        &self,
        node: Id,
        direction: Direction,
        rel: Option<&str>,
    ) -> EngineResult<Vec<(Id, Id)>> {
        self.node(node)?;
        let mut arcs = self.regular_arcs(node, direction, self.relation_filter(rel));
        arcs.sort_unstable_by_key(|&(_, edge)| edge);
        Ok(arcs)
    }

    fn create_index(&mut self, scope: Id, property: String) -> EngineResult<()> {
        if self.scope(scope)?.indexes.contains_key(&property) {
            return Ok(());
        }
        self.check_revision()?;
        let mut index = EqualityIndex::default();
        for &node in &self.scopes[&scope].members {
            if let Some(value) = self.node(node)?.attrs.get(&property) {
                index.add(node, value);
            }
        }
        self.scopes
            .get_mut(&scope)
            .unwrap()
            .indexes
            .insert(property, index);
        self.revision += 1;
        Ok(())
    }

    fn drop_index(&mut self, scope: Id, property: &str) -> EngineResult<()> {
        if !self.scope(scope)?.indexes.contains_key(property) {
            return Ok(());
        }
        self.check_revision()?;
        self.scopes
            .get_mut(&scope)
            .unwrap()
            .indexes
            .remove(property);
        self.revision += 1;
        Ok(())
    }

    fn find_nodes(
        &self,
        scope: Id,
        filters: &[Filter],
        recursive: bool,
        limit: Option<usize>,
    ) -> EngineResult<Vec<Id>> {
        let scopes = self.selected_scopes(scope, recursive)?;
        if limit == Some(0) {
            return Ok(Vec::new());
        }
        let mut matches = Vec::new();
        for scope in scopes {
            let scope = &self.scopes[&scope];
            let mut best: Option<&BTreeSet<Id>> = None;
            let mut empty = false;
            for filter in filters {
                if matches!(filter.op, Operator::Eq) {
                    if let Some(index) = scope.indexes.get(&filter.key) {
                        let key = IndexKey::new(&filter.value);
                        if let Some(posting) = index.postings.get(&key) {
                            // Plan using borrowed cardinalities; only iterate the winning posting.
                            if best.is_none_or(|best| posting.len() < best.len()) {
                                best = Some(posting);
                            }
                        } else {
                            empty = true;
                            break;
                        }
                    }
                }
            }
            if empty {
                continue;
            }
            for &node in best.unwrap_or(&scope.members) {
                let attrs = &self.nodes[self.node_positions[&node]].attrs;
                if filters.iter().all(|filter| filter.matches(attrs)) {
                    matches.push(node);
                    if !recursive && limit.is_some_and(|limit| matches.len() >= limit) {
                        return Ok(matches);
                    }
                }
            }
        }
        matches.sort_unstable();
        if let Some(limit) = limit {
            matches.truncate(limit);
        }
        Ok(matches)
    }

    fn traversal_arcs(
        &self,
        node: Id,
        direction: Direction,
        rel: RelationFilter,
        nested: bool,
    ) -> Vec<(Id, Option<Id>)> {
        let mut arcs: Vec<_> = self
            .regular_arcs(node, direction, rel)
            .into_iter()
            .map(|(node, edge)| (node, Some(edge)))
            .collect();
        if nested {
            let record = &self.nodes[self.node_positions[&node]];
            if !matches!(direction, Direction::In) {
                if let Some(child) = record.child_scope {
                    arcs.extend(self.scopes[&child].members.iter().map(|&node| (node, None)));
                }
            }
            if !matches!(direction, Direction::Out) {
                if let Some(owner) = self.scopes[&record.scope].owner {
                    arcs.push((owner, None));
                }
            }
        }
        arcs
    }

    fn bfs(&self, start: Id, options: &BfsOptions, stop: Option<Id>) -> EngineResult<BfsResult> {
        self.node(start)?;
        let mut result = BfsResult {
            nodes: vec![start],
            parents: vec![None],
            depths: vec![0],
            tree_edges: vec![None],
            positions: HashMap::from([(start, 0)]),
        };
        if stop == Some(start) {
            return Ok(result);
        }
        let relation = self.relation_filter(options.rel.as_deref());
        let mut cursor = 0;
        while cursor < result.nodes.len() {
            if options
                .max_nodes
                .is_some_and(|limit| result.nodes.len() >= limit)
            {
                break;
            }
            let node = result.nodes[cursor];
            let depth = result.depths[cursor];
            if options.max_depth.is_none_or(|limit| depth < limit) {
                for (neighbor, edge) in
                    self.traversal_arcs(node, options.direction, relation, options.nested)
                {
                    if result.positions.contains_key(&neighbor)
                        || options
                            .allowed
                            .as_ref()
                            .is_some_and(|allowed| !allowed.contains(&neighbor))
                    {
                        continue;
                    }
                    result.positions.insert(neighbor, result.nodes.len());
                    result.nodes.push(neighbor);
                    result.parents.push(Some(node));
                    result.depths.push(depth + 1);
                    result.tree_edges.push(edge);
                    if stop == Some(neighbor)
                        || options
                            .max_nodes
                            .is_some_and(|limit| result.nodes.len() >= limit)
                    {
                        return Ok(result);
                    }
                }
            }
            cursor += 1;
        }
        Ok(result)
    }

    fn shortest_path(
        &self,
        start: Id,
        end: Id,
        options: &BfsOptions,
    ) -> EngineResult<Option<Vec<Id>>> {
        self.node(end)?;
        let result = self.bfs(start, options, Some(end))?;
        let Some(&position) = result.positions.get(&end) else {
            return Ok(None);
        };
        let mut path = vec![end];
        let mut parent = result.parents[position];
        while let Some(node) = parent {
            path.push(node);
            parent = result.parents[result.positions[&node]];
        }
        path.reverse();
        Ok(Some(path))
    }

    fn connected_components(&self, scope: Id, recursive: bool) -> EngineResult<Vec<Vec<Id>>> {
        let nodes = self.node_ids(scope, recursive)?;
        let members: HashSet<_> = nodes.iter().copied().collect();
        let mut visited = HashSet::new();
        let mut components = Vec::new();
        for node in nodes {
            if !visited.insert(node) {
                continue;
            }
            let mut component = Vec::new();
            let mut queue = VecDeque::from([node]);
            while let Some(node) = queue.pop_front() {
                component.push(node);
                for (neighbor, _) in self.regular_arcs(node, Direction::Both, RelationFilter::Any) {
                    if members.contains(&neighbor) && visited.insert(neighbor) {
                        queue.push_back(neighbor);
                    }
                }
            }
            component.sort_unstable();
            components.push(component);
        }
        Ok(components)
    }

    fn topological_sort(&self, scope: Id, recursive: bool) -> EngineResult<Option<Vec<Id>>> {
        let nodes = self.node_ids(scope, recursive)?;
        let positions: HashMap<_, _> = nodes
            .iter()
            .enumerate()
            .map(|(position, &id)| (id, position))
            .collect();
        let mut indegrees = vec![0usize; nodes.len()];
        for &node in &nodes {
            for (neighbor, _) in self.regular_arcs(node, Direction::Out, RelationFilter::Any) {
                if let Some(&position) = positions.get(&neighbor) {
                    indegrees[position] += 1;
                }
            }
        }
        let mut ready: BinaryHeap<_> = nodes
            .iter()
            .enumerate()
            .filter_map(|(position, &id)| (indegrees[position] == 0).then_some(Reverse(id)))
            .collect();
        let mut result = Vec::with_capacity(nodes.len());
        while let Some(Reverse(node)) = ready.pop() {
            result.push(node);
            for (neighbor, _) in self.regular_arcs(node, Direction::Out, RelationFilter::Any) {
                if let Some(&position) = positions.get(&neighbor) {
                    indegrees[position] -= 1;
                    if indegrees[position] == 0 {
                        ready.push(Reverse(neighbor));
                    }
                }
            }
        }
        Ok((result.len() == nodes.len()).then_some(result))
    }

    fn stats(&self, scope: Id, recursive: bool) -> EngineResult<BTreeMap<String, u64>> {
        let scopes = self.selected_scopes(scope, recursive)?;
        Ok(BTreeMap::from([
            (
                "nodes".into(),
                scopes
                    .iter()
                    .map(|scope| self.scopes[scope].members.len() as u64)
                    .sum(),
            ),
            (
                "edges".into(),
                scopes
                    .iter()
                    .map(|scope| self.scopes[scope].edges.len() as u64)
                    .sum(),
            ),
            ("scopes".into(), scopes.len() as u64),
            ("revision".into(), self.revision),
        ]))
    }

    fn memory_usage(&self) -> BTreeMap<String, usize> {
        let mut nodes_bytes = size_of::<Self>()
            + self.nodes.capacity() * size_of::<Node>()
            + hash_bytes::<Id, usize>(self.node_positions.capacity())
            + hash_bytes::<Id, Scope>(self.scopes.capacity());
        let mut edges_bytes = self.edges.capacity() * size_of::<Edge>()
            + hash_bytes::<Id, usize>(self.edge_positions.capacity())
            + hash_bytes::<(Id, Id, Id), Id>(self.edge_keys.capacity())
            + self.relations.capacity() * size_of::<Relation>()
            + hash_bytes::<String, Id>(self.relation_ids.capacity());
        let mut indexes_bytes = 0;
        let mut properties_bytes = hash_bytes::<Arc<str>, ()>(self.property_keys.capacity())
            + self
                .property_keys
                .iter()
                .map(|key| key.len() + 2 * size_of::<usize>())
                .sum::<usize>();
        for node in &self.nodes {
            nodes_bytes += node.local_id.capacity();
            edges_bytes += (node.outgoing.capacity() + node.incoming.capacity()) * size_of::<Id>();
            properties_bytes += properties_heap_bytes(&node.attrs);
        }
        for edge in &self.edges {
            properties_bytes += properties_heap_bytes(&edge.attrs);
        }
        for relation in &self.relations {
            edges_bytes += relation.name.capacity() + relation.edges.capacity() * size_of::<Id>();
        }
        edges_bytes += self
            .relation_ids
            .keys()
            .map(String::capacity)
            .sum::<usize>();
        for scope in self.scopes.values() {
            nodes_bytes += hash_bytes::<String, Id>(scope.names.capacity())
                + scope.names.keys().map(String::capacity).sum::<usize>()
                + tree_bytes::<Id>(scope.members.len());
            edges_bytes += scope.edges.capacity() * size_of::<Id>();
            indexes_bytes += hash_bytes::<String, EqualityIndex>(scope.indexes.capacity());
            for (property, index) in &scope.indexes {
                indexes_bytes += property.capacity()
                    + hash_bytes::<IndexKey, BTreeSet<Id>>(index.postings.capacity());
                for (key, posting) in &index.postings {
                    indexes_bytes += key.heap_bytes() + tree_bytes::<Id>(posting.len());
                }
            }
        }
        BTreeMap::from([
            ("nodes_bytes".into(), nodes_bytes),
            ("edges_bytes".into(), edges_bytes),
            ("indexes_bytes".into(), indexes_bytes),
            ("properties_bytes".into(), properties_bytes),
            (
                "total_bytes".into(),
                nodes_bytes + edges_bytes + indexes_bytes + properties_bytes,
            ),
        ])
    }
}

struct BfsOptions {
    max_depth: Option<usize>,
    direction: Direction,
    rel: Option<String>,
    nested: bool,
    max_nodes: Option<usize>,
    allowed: Option<HashSet<Id>>,
}

struct BfsResult {
    nodes: Vec<Id>,
    parents: Vec<Option<Id>>,
    depths: Vec<usize>,
    tree_edges: Vec<Option<Id>>,
    positions: HashMap<Id, usize>,
}

impl BfsResult {
    fn into_arrays(self) -> BfsArrays {
        (self.nodes, self.parents, self.depths, self.tree_edges)
    }
}

fn nonnegative(value: Option<i64>, name: &str) -> EngineResult<Option<usize>> {
    value
        .map(|value| usize::try_from(value).map_err(|_| invalid(format!("{name} must be >= 0"))))
        .transpose()
}

fn bfs_options(
    max_depth: Option<i64>,
    direction: &str,
    rel: Option<String>,
    nested: bool,
    max_nodes: Option<i64>,
    allowed: Option<Vec<Id>>,
) -> EngineResult<BfsOptions> {
    if max_nodes.is_some_and(|value| value < 1) {
        return Err(invalid("max_nodes must be >= 1"));
    }
    Ok(BfsOptions {
        max_depth: nonnegative(max_depth, "max_depth")?,
        direction: Direction::parse(direction)?,
        rel,
        nested,
        max_nodes: nonnegative(max_nodes, "max_nodes")?,
        allowed: allowed.map(|nodes| nodes.into_iter().collect()),
    })
}

fn hash_bytes<K, V>(capacity: usize) -> usize {
    capacity * (size_of::<(K, V)>() + 1) + capacity / 7
}

fn tree_bytes<T>(length: usize) -> usize {
    length.div_ceil(7) * (11 * size_of::<T>() + 3 * size_of::<usize>())
        + length.div_ceil(49) * 12 * size_of::<usize>()
}

fn value_heap_bytes(value: &Value) -> usize {
    match value {
        Value::String(value) => value.capacity(),
        Value::Array(values) => {
            values.capacity() * size_of::<Value>()
                + values.iter().map(value_heap_bytes).sum::<usize>()
        }
        Value::Object(properties) => {
            tree_bytes::<(String, Value)>(properties.len())
                + properties
                    .iter()
                    .map(|(key, value)| key.capacity() + value_heap_bytes(value))
                    .sum::<usize>()
        }
        _ => 0,
    }
}

fn properties_heap_bytes(properties: &Properties) -> usize {
    properties.values.capacity() * size_of::<(Arc<str>, Value)>()
        + properties.values().map(value_heap_bytes).sum::<usize>()
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct Snapshot {
    version: u32,
    revision: u64,
    next_node_id: u64,
    next_edge_id: u64,
    next_scope_id: u64,
    scopes: Vec<SnapshotScope>,
    nodes: Vec<SnapshotNode>,
    edges: Vec<SnapshotEdge>,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct SnapshotScope {
    id: Id,
    owner: Option<Id>,
    indexes: Vec<String>,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct SnapshotNode {
    id: Id,
    scope: Id,
    local_id: String,
    child_scope: Option<Id>,
    #[serde(deserialize_with = "deserialize_properties")]
    attrs: Properties,
}

#[derive(Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
struct SnapshotEdge {
    id: Id,
    src: Id,
    dst: Id,
    rel: String,
    #[serde(deserialize_with = "deserialize_properties")]
    attrs: Properties,
}

// Raw validation keeps oversized JSON integer literals from serde_json's f64 fallback.
fn validate_json_numbers(raw: &str) -> EngineResult<Cow<'_, str>> {
    let bytes = raw.as_bytes();
    let mut cursor = 0;
    let mut normalized: Option<Vec<u8>> = None;
    while cursor < bytes.len() {
        if bytes[cursor] == b'"' {
            cursor += 1;
            while cursor < bytes.len() {
                match bytes[cursor] {
                    b'\\' => cursor += 2,
                    b'"' => {
                        cursor += 1;
                        break;
                    }
                    _ => cursor += 1,
                }
            }
        } else if bytes[cursor] == b'-' || bytes[cursor].is_ascii_digit() {
            let start = cursor;
            cursor += 1;
            while cursor < bytes.len()
                && (bytes[cursor].is_ascii_digit()
                    || matches!(bytes[cursor], b'.' | b'e' | b'E' | b'+' | b'-'))
            {
                cursor += 1;
            }
            let number = &raw[start..cursor];
            if number.contains(['.', 'e', 'E']) {
                if !number.parse::<f64>().is_ok_and(f64::is_finite) {
                    return Err(invalid("property floats must be finite"));
                }
            } else if number.parse::<i64>().is_err() {
                return Err(invalid("property integers must fit signed 64 bits"));
            } else if number == "-0" {
                // serde_json treats lexical -0 as f64; keep JSON integer equality typed.
                normalized.get_or_insert_with(|| bytes.to_vec())[start] = b' ';
            }
        } else {
            cursor += 1;
        }
    }
    match normalized {
        Some(bytes) => String::from_utf8(bytes)
            .map(Cow::Owned)
            .map_err(|error| invalid(format!("invalid property JSON: {error}"))),
        None => Ok(Cow::Borrowed(raw)),
    }
}

struct StrictValue(Value);

impl<'de> Deserialize<'de> for StrictValue {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<Self, D::Error> {
        struct ValueVisitor;
        impl<'de> Visitor<'de> for ValueVisitor {
            type Value = StrictValue;
            fn expecting(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
                formatter.write_str("a JSON property value")
            }
            fn visit_unit<E: de::Error>(self) -> Result<Self::Value, E> {
                Ok(StrictValue(Value::Null))
            }
            fn visit_bool<E: de::Error>(self, value: bool) -> Result<Self::Value, E> {
                Ok(StrictValue(Value::Bool(value)))
            }
            fn visit_i64<E: de::Error>(self, value: i64) -> Result<Self::Value, E> {
                Ok(StrictValue(Value::Number(value.into())))
            }
            fn visit_u64<E: de::Error>(self, value: u64) -> Result<Self::Value, E> {
                let value = i64::try_from(value)
                    .map_err(|_| E::custom("property integers must fit signed 64 bits"))?;
                Ok(StrictValue(Value::Number(value.into())))
            }
            fn visit_f64<E: de::Error>(self, value: f64) -> Result<Self::Value, E> {
                Number::from_f64(value)
                    .map(|value| StrictValue(Value::Number(value)))
                    .ok_or_else(|| E::custom("property floats must be finite"))
            }
            fn visit_str<E: de::Error>(self, value: &str) -> Result<Self::Value, E> {
                Ok(StrictValue(Value::String(value.into())))
            }
            fn visit_string<E: de::Error>(self, value: String) -> Result<Self::Value, E> {
                Ok(StrictValue(Value::String(value)))
            }
            fn visit_seq<A: SeqAccess<'de>>(
                self,
                mut sequence: A,
            ) -> Result<Self::Value, A::Error> {
                let mut values = Vec::new();
                while let Some(StrictValue(value)) = sequence.next_element()? {
                    values.push(value);
                }
                Ok(StrictValue(Value::Array(values)))
            }
            fn visit_map<A: MapAccess<'de>>(self, mut map: A) -> Result<Self::Value, A::Error> {
                let mut values = Map::new();
                while let Some(key) = map.next_key::<String>()? {
                    if values.contains_key(&key) {
                        return Err(de::Error::custom("duplicate property key"));
                    }
                    let StrictValue(value) = map.next_value()?;
                    values.insert(key, value);
                }
                Ok(StrictValue(Value::Object(values)))
            }
        }
        deserializer.deserialize_any(ValueVisitor)
    }
}

fn deserialize_properties<'de, D: Deserializer<'de>>(
    deserializer: D,
) -> Result<Properties, D::Error> {
    let raw = Box::<serde_json::value::RawValue>::deserialize(deserializer)?;
    let normalized = validate_json_numbers(raw.get()).map_err(de::Error::custom)?;
    let StrictValue(value) = serde_json::from_str(&normalized).map_err(de::Error::custom)?;
    let Value::Object(properties) = value else {
        return Err(de::Error::custom("properties must be an object"));
    };
    let properties = Properties::from(properties);
    validate_properties(&properties).map_err(de::Error::custom)?;
    Ok(properties)
}

impl Store {
    fn snapshot(&self) -> EngineResult<Vec<u8>> {
        let mut scopes: Vec<_> = self
            .scopes
            .iter()
            .map(|(&id, scope)| {
                let mut indexes: Vec<_> = scope.indexes.keys().cloned().collect();
                indexes.sort_unstable();
                SnapshotScope {
                    id,
                    owner: scope.owner,
                    indexes,
                }
            })
            .collect();
        scopes.sort_unstable_by_key(|scope| scope.id);
        let mut nodes: Vec<_> = self
            .nodes
            .iter()
            .map(|node| SnapshotNode {
                id: node.id,
                scope: node.scope,
                local_id: node.local_id.clone(),
                child_scope: node.child_scope,
                attrs: node.attrs.clone(),
            })
            .collect();
        nodes.sort_unstable_by_key(|node| node.id);
        let mut edges: Vec<_> = self
            .edges
            .iter()
            .map(|edge| SnapshotEdge {
                id: edge.id,
                src: edge.src,
                dst: edge.dst,
                rel: self.relations[edge.rel as usize].name.clone(),
                attrs: edge.attrs.clone(),
            })
            .collect();
        edges.sort_unstable_by_key(|edge| edge.id);
        let snapshot = Snapshot {
            version: SNAPSHOT_VERSION,
            revision: self.revision,
            next_node_id: self.next_node_id,
            next_edge_id: self.next_edge_id,
            next_scope_id: self.next_scope_id,
            scopes,
            nodes,
            edges,
        };
        serde_json::to_vec(&snapshot)
            .map_err(|error| invalid(format!("snapshot serialization failed: {error}")))
    }

    fn from_snapshot(data: &[u8]) -> EngineResult<Self> {
        let snapshot: Snapshot = serde_json::from_slice(data)
            .map_err(|error| invalid(format!("invalid snapshot: {error}")))?;
        if snapshot.version != SNAPSHOT_VERSION {
            return Err(invalid("unsupported native snapshot version"));
        }
        if snapshot.next_node_id > ID_LIMIT
            || snapshot.next_edge_id > ID_LIMIT
            || snapshot.next_scope_id == 0
            || snapshot.next_scope_id > ID_LIMIT
        {
            return Err(invalid("invalid snapshot ID high-watermarks"));
        }
        let mut store = Self {
            revision: snapshot.revision,
            next_node_id: snapshot.next_node_id,
            next_edge_id: snapshot.next_edge_id,
            next_scope_id: snapshot.next_scope_id,
            ..Self::default()
        };
        store.scopes.clear();
        for scope in snapshot.scopes {
            if scope.id as u64 >= store.next_scope_id || store.scopes.contains_key(&scope.id) {
                return Err(invalid("duplicate scope or invalid scope high-watermark"));
            }
            if (scope.id == 0) != scope.owner.is_none() {
                return Err(invalid("only root scope 0 may have no owner"));
            }
            let mut indexes = HashMap::new();
            for property in scope.indexes {
                if indexes.insert(property, EqualityIndex::default()).is_some() {
                    return Err(invalid("duplicate index definition"));
                }
            }
            store.scopes.insert(
                scope.id,
                Scope {
                    owner: scope.owner,
                    indexes,
                    ..Scope::default()
                },
            );
        }
        if !store.scopes.contains_key(&0) {
            return Err(invalid("snapshot is missing root scope 0"));
        }
        for mut node in snapshot.nodes {
            if node.id as u64 >= store.next_node_id || store.node_positions.contains_key(&node.id) {
                return Err(invalid("duplicate node or invalid node high-watermark"));
            }
            let Some(scope) = store.scopes.get_mut(&node.scope) else {
                return Err(invalid("node references missing scope"));
            };
            if scope.names.insert(node.local_id.clone(), node.id).is_some() {
                return Err(invalid("duplicate local node ID in a scope"));
            }
            scope.members.insert(node.id);
            node.attrs.intern_keys(&mut store.property_keys);
            for (property, index) in &mut scope.indexes {
                if let Some(value) = node.attrs.get(property) {
                    index.add(node.id, value);
                }
            }
            store.node_positions.insert(node.id, store.nodes.len());
            store.nodes.push(Node {
                id: node.id,
                scope: node.scope,
                local_id: node.local_id,
                child_scope: node.child_scope,
                attrs: node.attrs,
                outgoing: Vec::new(),
                incoming: Vec::new(),
            });
        }
        for (&id, scope) in &store.scopes {
            if let Some(owner) = scope.owner {
                let node = store
                    .node(owner)
                    .map_err(|_| invalid("scope references missing owner"))?;
                if node.child_scope != Some(id) {
                    return Err(invalid("scope ownership and node child_scope disagree"));
                }
            }
        }
        for node in &store.nodes {
            if let Some(child) = node.child_scope {
                if child == 0
                    || store
                        .scopes
                        .get(&child)
                        .is_none_or(|scope| scope.owner != Some(node.id))
                {
                    return Err(invalid("node references invalid child scope"));
                }
            }
        }
        let mut reached = HashSet::from([0]);
        let mut queue = VecDeque::from([0]);
        while let Some(scope) = queue.pop_front() {
            for &node in &store.scopes[&scope].members {
                if let Some(child) = store.nodes[store.node_positions[&node]].child_scope {
                    if !reached.insert(child) {
                        return Err(invalid("snapshot scope hierarchy contains a cycle"));
                    }
                    queue.push_back(child);
                }
            }
        }
        if reached.len() != store.scopes.len() {
            return Err(invalid("snapshot hierarchy is disconnected or cyclic"));
        }
        for mut edge in snapshot.edges {
            if edge.id as u64 >= store.next_edge_id || store.edge_positions.contains_key(&edge.id) {
                return Err(invalid("duplicate edge or invalid edge high-watermark"));
            }
            if !store.node_positions.contains_key(&edge.src)
                || !store.node_positions.contains_key(&edge.dst)
            {
                return Err(invalid("edge references missing endpoint"));
            }
            Self::check_ids(
                store.relations.len() as u64,
                usize::from(!store.relation_ids.contains_key(&edge.rel)),
                "relation",
            )?;
            let rel = store.intern_relation(&edge.rel);
            if store.edge_keys.contains_key(&(edge.src, edge.dst, rel)) {
                return Err(invalid("duplicate edge triple"));
            }
            edge.attrs.intern_keys(&mut store.property_keys);
            store.insert_edge(edge.id, edge.src, edge.dst, rel, edge.attrs);
        }
        Ok(store)
    }
}

#[pyclass(module = "fastgraph._native", frozen)]
struct NativeStore {
    inner: Arc<RwLock<Store>>,
}

impl NativeStore {
    fn quick_read<T>(&self, work: impl FnOnce(&Store) -> EngineResult<T>) -> PyResult<T> {
        let store = self
            .inner
            .read()
            .map_err(|_| PyRuntimeError::new_err("native store lock poisoned"))?;
        work(&store).map_err(Into::into)
    }

    fn read<T: Send>(
        &self,
        py: Python<'_>,
        work: impl FnOnce(&Store) -> EngineResult<T> + Send,
    ) -> PyResult<T> {
        let inner = Arc::clone(&self.inner);
        py.detach(move || {
            let store = inner
                .read()
                .map_err(|_| EngineError::State("native store lock poisoned".into()))?;
            work(&store)
        })
        .map_err(Into::into)
    }

    fn write<T: Send>(
        &self,
        py: Python<'_>,
        work: impl FnOnce(&mut Store) -> EngineResult<T> + Send,
    ) -> PyResult<T> {
        let inner = Arc::clone(&self.inner);
        py.detach(move || {
            let mut store = inner
                .write()
                .map_err(|_| EngineError::State("native store lock poisoned".into()))?;
            work(&mut store)
        })
        .map_err(Into::into)
    }
}

#[pymethods]
impl NativeStore {
    #[new]
    fn new() -> Self {
        Self {
            inner: Arc::new(RwLock::new(Store::default())),
        }
    }

    #[getter]
    fn revision(&self) -> PyResult<u64> {
        self.quick_read(|store| Ok(store.revision))
    }

    fn node_id(&self, scope: Id, local_id: &str) -> PyResult<Option<Id>> {
        self.quick_read(move |store| Ok(store.scope(scope)?.names.get(local_id).copied()))
    }

    fn node_info(&self, node: Id) -> PyResult<(Id, String, Option<Id>)> {
        self.quick_read(move |store| {
            let node = store.node(node)?;
            Ok((node.scope, node.local_id.clone(), node.child_scope))
        })
    }

    fn get_node<'py>(&self, py: Python<'py>, node: Id) -> PyResult<Bound<'py, PyDict>> {
        let attrs = self.quick_read(move |store| Ok(store.node(node)?.attrs.clone()))?;
        properties_to_python(py, &attrs)
    }

    fn has_node(&self, node: Id) -> PyResult<bool> {
        self.quick_read(move |store| Ok(store.node_positions.contains_key(&node)))
    }

    #[pyo3(signature = (scope, recursive=false))]
    fn node_ids(&self, py: Python<'_>, scope: Id, recursive: bool) -> PyResult<Vec<Id>> {
        self.read(py, move |store| store.node_ids(scope, recursive))
    }

    fn scope_owner(&self, scope: Id) -> PyResult<Option<Id>> {
        self.quick_read(move |store| Ok(store.scope(scope)?.owner))
    }

    fn scope_exists(&self, scope: Id) -> PyResult<bool> {
        self.quick_read(move |store| Ok(store.scopes.contains_key(&scope)))
    }

    fn create_scope(&self, py: Python<'_>, owner: Id) -> PyResult<Id> {
        self.write(py, move |store| store.create_scope(owner))
    }

    fn clear_scope(&self, py: Python<'_>, scope: Id) -> PyResult<()> {
        self.write(py, move |store| store.clear_scope(scope))
    }

    fn add_nodes(
        &self,
        py: Python<'_>,
        scope: Id,
        nodes: Vec<(String, Py<PyAny>)>,
    ) -> PyResult<Vec<Id>> {
        let nodes = nodes
            .into_iter()
            .map(|(name, attrs)| Ok((name, properties_from_python(attrs.bind(py))?)))
            .collect::<PyResult<Vec<_>>>()?;
        self.write(py, move |store| store.add_nodes(scope, nodes))
    }

    fn remove_node(&self, py: Python<'_>, node: Id) -> PyResult<bool> {
        self.write(py, move |store| store.remove_node(node))
    }

    fn add_edges(
        &self,
        py: Python<'_>,
        edges: Vec<(Id, Id, String, Py<PyAny>)>,
    ) -> PyResult<Vec<Id>> {
        let edges = edges
            .into_iter()
            .map(|(src, dst, rel, attrs)| {
                Ok((src, dst, rel, properties_from_python(attrs.bind(py))?))
            })
            .collect::<PyResult<Vec<_>>>()?;
        self.write(py, move |store| store.add_edges(edges))
    }

    fn add_edges_local(
        &self,
        py: Python<'_>,
        scope: Id,
        edges: Vec<(String, String, String, Py<PyAny>)>,
    ) -> PyResult<Vec<Id>> {
        let edges = edges
            .into_iter()
            .map(|(src, dst, rel, attrs)| {
                Ok((src, dst, rel, properties_from_python(attrs.bind(py))?))
            })
            .collect::<PyResult<Vec<_>>>()?;
        self.write(py, move |store| store.add_edges_local(scope, edges))
    }

    fn edge_id(&self, src: Id, dst: Id, rel: &str) -> PyResult<Option<Id>> {
        self.quick_read(move |store| {
            Ok(store
                .relation_ids
                .get(rel)
                .and_then(|&rel| store.edge_keys.get(&(src, dst, rel)))
                .copied())
        })
    }

    fn edge_local<'py>(
        &self,
        py: Python<'py>,
        scope: Id,
        src: &str,
        dst: &str,
        rel: &str,
    ) -> PyResult<Option<(Id, Bound<'py, PyDict>)>> {
        let edge = self.quick_read(|store| {
            store
                .edge_local_id(scope, src, dst, rel)?
                .map(|id| Ok((id, store.edge(id)?.attrs.clone())))
                .transpose()
        })?;
        edge.map(|(id, attrs)| Ok((id, properties_to_python(py, &attrs)?)))
            .transpose()
    }

    fn has_edge_local(&self, scope: Id, src: &str, dst: &str, rel: &str) -> PyResult<bool> {
        self.quick_read(|store| Ok(store.edge_local_id(scope, src, dst, rel)?.is_some()))
    }

    fn get_edge<'py>(
        &self,
        py: Python<'py>,
        edge: Id,
    ) -> PyResult<(Id, Id, String, Bound<'py, PyDict>)> {
        let (src, dst, rel, attrs) = self.quick_read(move |store| {
            let edge = store.edge(edge)?;
            Ok((
                edge.src,
                edge.dst,
                store.relations[edge.rel as usize].name.clone(),
                edge.attrs.clone(),
            ))
        })?;
        Ok((src, dst, rel, properties_to_python(py, &attrs)?))
    }

    #[pyo3(signature = (scope, recursive=false, src=None, dst=None, rel=None, filters=Vec::new()))]
    #[allow(clippy::too_many_arguments)]
    fn edge_ids(
        &self,
        py: Python<'_>,
        scope: Id,
        recursive: bool,
        src: Option<Id>,
        dst: Option<Id>,
        rel: Option<String>,
        filters: PythonFilters,
    ) -> PyResult<Vec<Id>> {
        let filters = filters_from_python(py, filters)?;
        self.read(py, move |store| {
            store.edge_ids(scope, recursive, src, dst, rel.as_deref(), &filters)
        })
    }

    fn remove_edges(&self, py: Python<'_>, edges: Vec<Id>) -> PyResult<usize> {
        self.write(py, move |store| store.remove_edges(edges))
    }

    #[pyo3(signature = (node, direction="out", rel=None))]
    fn neighbors(
        &self,
        py: Python<'_>,
        node: Id,
        direction: &str,
        rel: Option<String>,
    ) -> PyResult<Vec<(Id, Id)>> {
        let direction = Direction::parse(direction)?;
        self.read(py, move |store| {
            store.neighbors(node, direction, rel.as_deref())
        })
    }

    fn degree(&self, node: Id) -> PyResult<(usize, usize)> {
        self.quick_read(move |store| {
            let node = store.node(node)?;
            Ok((node.outgoing.len(), node.incoming.len()))
        })
    }

    fn create_index(&self, py: Python<'_>, scope: Id, property: String) -> PyResult<()> {
        self.write(py, move |store| store.create_index(scope, property))
    }

    fn drop_index(&self, py: Python<'_>, scope: Id, property: String) -> PyResult<()> {
        self.write(py, move |store| store.drop_index(scope, &property))
    }

    fn index_names(&self, py: Python<'_>, scope: Id) -> PyResult<Vec<String>> {
        self.read(py, move |store| {
            let mut names: Vec<_> = store.scope(scope)?.indexes.keys().cloned().collect();
            names.sort_unstable();
            Ok(names)
        })
    }

    #[pyo3(signature = (scope, filters, recursive=false, limit=None))]
    fn find_nodes(
        &self,
        py: Python<'_>,
        scope: Id,
        filters: PythonFilters,
        recursive: bool,
        limit: Option<i64>,
    ) -> PyResult<Vec<Id>> {
        let filters = filters_from_python(py, filters)?;
        let limit = nonnegative(limit, "limit")?;
        self.read(py, move |store| {
            store.find_nodes(scope, &filters, recursive, limit)
        })
    }

    #[pyo3(signature = (start, max_depth=None, direction="out", rel=None, nested=false, max_nodes=None, allowed=None))]
    #[allow(clippy::too_many_arguments)]
    fn bfs(
        &self,
        py: Python<'_>,
        start: Id,
        max_depth: Option<i64>,
        direction: &str,
        rel: Option<String>,
        nested: bool,
        max_nodes: Option<i64>,
        allowed: Option<Vec<Id>>,
    ) -> PyResult<BfsArrays> {
        let options = bfs_options(max_depth, direction, rel, nested, max_nodes, allowed)?;
        self.read(py, move |store| {
            Ok(store.bfs(start, &options, None)?.into_arrays())
        })
    }

    #[pyo3(signature = (start, end, direction="out", rel=None, nested=false, max_depth=None))]
    #[allow(clippy::too_many_arguments)]
    fn shortest_path(
        &self,
        py: Python<'_>,
        start: Id,
        end: Id,
        direction: &str,
        rel: Option<String>,
        nested: bool,
        max_depth: Option<i64>,
    ) -> PyResult<Option<Vec<Id>>> {
        let options = bfs_options(max_depth, direction, rel, nested, None, None)?;
        self.read(py, move |store| store.shortest_path(start, end, &options))
    }

    #[pyo3(signature = (scope, recursive=false))]
    fn connected_components(
        &self,
        py: Python<'_>,
        scope: Id,
        recursive: bool,
    ) -> PyResult<Vec<Vec<Id>>> {
        self.read(py, move |store| {
            store.connected_components(scope, recursive)
        })
    }

    #[pyo3(signature = (scope, recursive=false))]
    fn topological_sort(
        &self,
        py: Python<'_>,
        scope: Id,
        recursive: bool,
    ) -> PyResult<Option<Vec<Id>>> {
        self.read(py, move |store| store.topological_sort(scope, recursive))
    }

    #[pyo3(signature = (scope, recursive=false))]
    fn stats(&self, py: Python<'_>, scope: Id, recursive: bool) -> PyResult<BTreeMap<String, u64>> {
        self.read(py, move |store| store.stats(scope, recursive))
    }

    fn memory_usage(&self, py: Python<'_>) -> PyResult<BTreeMap<String, usize>> {
        self.read(py, |store| Ok(store.memory_usage()))
    }

    fn snapshot<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyBytes>> {
        let bytes = self.read(py, Store::snapshot)?;
        Ok(PyBytes::new(py, &bytes))
    }

    #[staticmethod]
    fn from_snapshot(py: Python<'_>, data: &Bound<'_, PyBytes>) -> PyResult<Self> {
        let bytes = data.as_bytes().to_vec();
        let store = py.detach(move || Store::from_snapshot(&bytes))?;
        Ok(Self {
            inner: Arc::new(RwLock::new(store)),
        })
    }

    fn clone(&self, py: Python<'_>) -> PyResult<Self> {
        let store = self.read(py, |store| Ok(store.clone()))?;
        Ok(Self {
            inner: Arc::new(RwLock::new(store)),
        })
    }
}

#[pymodule]
fn _native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<NativeStore>()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::ffi::CString;

    fn attrs(value: Value) -> Properties {
        value.as_object().unwrap().clone().into()
    }

    fn add(store: &mut Store, scope: Id, names: &[&str]) -> Vec<Id> {
        store
            .add_nodes(
                scope,
                names
                    .iter()
                    .map(|name| ((*name).into(), Properties::new()))
                    .collect(),
            )
            .unwrap()
    }

    fn edge(store: &mut Store, src: Id, dst: Id, rel: &str) -> Id {
        store
            .add_edges(vec![(src, dst, rel.into(), Properties::new())])
            .unwrap()[0]
    }

    fn filter(key: &str, op: &str, value: Value) -> Filter {
        Filter::new(key.into(), op, value).unwrap()
    }

    fn find(store: &Store, scope: Id, key: &str, op: &str, value: Value) -> Vec<Id> {
        store
            .find_nodes(scope, &[filter(key, op, value)], false, None)
            .unwrap()
    }

    fn options(direction: &str, nested: bool) -> BfsOptions {
        bfs_options(None, direction, None, nested, None, None).unwrap()
    }

    fn assert_integrity(store: &Store) {
        assert_eq!(store.nodes.len(), store.node_positions.len());
        assert_eq!(store.edges.len(), store.edge_positions.len());
        assert_eq!(store.edges.len(), store.edge_keys.len());
        for (position, node) in store.nodes.iter().enumerate() {
            assert_eq!(store.node_positions[&node.id], position);
            assert!(u64::from(node.id) < store.next_node_id);
            let scope = &store.scopes[&node.scope];
            assert_eq!(scope.names[&node.local_id], node.id);
            assert!(scope.members.contains(&node.id));
            if let Some(child) = node.child_scope {
                assert_eq!(store.scopes[&child].owner, Some(node.id));
            }
            assert_eq!(
                node.outgoing.len(),
                node.outgoing.iter().collect::<HashSet<_>>().len()
            );
            assert_eq!(
                node.incoming.len(),
                node.incoming.iter().collect::<HashSet<_>>().len()
            );
            for (position, &id) in node.outgoing.iter().enumerate() {
                let edge = store.edge(id).unwrap();
                assert_eq!((edge.src, edge.out_pos), (node.id, position));
            }
            for (position, &id) in node.incoming.iter().enumerate() {
                let edge = store.edge(id).unwrap();
                assert_eq!((edge.dst, edge.in_pos), (node.id, position));
            }
        }
        for (position, edge) in store.edges.iter().enumerate() {
            assert_eq!(store.edge_positions[&edge.id], position);
            assert!(u64::from(edge.id) < store.next_edge_id);
            assert_eq!(store.edge_keys[&(edge.src, edge.dst, edge.rel)], edge.id);
            assert_eq!(
                store.node(edge.src).unwrap().outgoing[edge.out_pos],
                edge.id
            );
            assert_eq!(store.node(edge.dst).unwrap().incoming[edge.in_pos], edge.id);
            assert_eq!(
                store.relations[edge.rel as usize].edges[edge.rel_pos],
                edge.id
            );
            let scope = store.node(edge.src).unwrap().scope;
            assert_eq!(store.scopes[&scope].edges[edge.scope_pos], edge.id);
        }
        for (&id, scope) in &store.scopes {
            assert!(u64::from(id) < store.next_scope_id);
            assert_eq!(scope.names.len(), scope.members.len());
            if let Some(owner) = scope.owner {
                assert_eq!(store.node(owner).unwrap().child_scope, Some(id));
            } else {
                assert_eq!(id, 0);
            }
            for &node in &scope.members {
                assert_eq!(store.node(node).unwrap().scope, id);
            }
            for (position, &edge) in scope.edges.iter().enumerate() {
                let edge = store.edge(edge).unwrap();
                assert_eq!(edge.scope_pos, position);
                assert_eq!(store.node(edge.src).unwrap().scope, id);
            }
            for (property, index) in &scope.indexes {
                let mut expected = EqualityIndex::default();
                for &node in &scope.members {
                    if let Some(value) = store.node(node).unwrap().attrs.get(property) {
                        expected.add(node, value);
                    }
                }
                assert_eq!(expected.postings, index.postings);
            }
        }
        for (id, relation) in store.relations.iter().enumerate() {
            assert_eq!(store.relation_ids[&relation.name] as usize, id);
            for (position, &edge) in relation.edges.iter().enumerate() {
                let edge = store.edge(edge).unwrap();
                assert_eq!((edge.rel as usize, edge.rel_pos), (id, position));
            }
        }
    }

    #[test]
    fn duplicate_edges_replace_without_duplicate_adjacency_and_deletion_fixes_positions() {
        let mut store = Store::default();
        let nodes = add(&mut store, 0, &["a", "b", "c"]);
        let first = store
            .add_edges(vec![(
                nodes[0],
                nodes[1],
                "r".into(),
                attrs(json!({"old": true})),
            )])
            .unwrap()[0];
        let replaced = store
            .add_edges(vec![
                (nodes[0], nodes[1], "r".into(), attrs(json!({"version": 1}))),
                (nodes[0], nodes[1], "r".into(), attrs(json!({"version": 2}))),
            ])
            .unwrap();
        assert_eq!(replaced, [first, first]);
        assert_eq!(store.edges.len(), 1);
        assert_eq!(store.node(nodes[0]).unwrap().outgoing, [first]);
        assert_eq!(store.node(nodes[1]).unwrap().incoming, [first]);
        assert_eq!(
            store.edge(first).unwrap().attrs,
            attrs(json!({"version": 2}))
        );
        let second = edge(&mut store, nodes[0], nodes[2], "r");
        let third = edge(&mut store, nodes[2], nodes[1], "r");
        let loop_id = edge(&mut store, nodes[1], nodes[1], "loop");
        assert_eq!(
            store
                .neighbors(nodes[1], Direction::Both, Some("loop"))
                .unwrap(),
            [(nodes[1], loop_id)]
        );
        assert_eq!(store.remove_edges(vec![first, first, u32::MAX]).unwrap(), 1);
        assert_integrity(&store);
        assert_eq!(store.remove_edges(vec![third, loop_id, second]).unwrap(), 3);
        assert!(store.edges.is_empty());
        assert!(store.node(nodes[0]).unwrap().outgoing.is_empty());
        assert!(store.node(nodes[1]).unwrap().incoming.is_empty());
        let future = edge(&mut store, nodes[0], nodes[1], "r");
        assert!(future > loop_id);
        assert!(!store.edge_positions.contains_key(&first));
        assert_integrity(&store);
    }

    #[test]
    fn dense_edge_removal_and_star_node_cleanup_do_not_leave_ghosts() {
        let mut store = Store::default();
        let nodes = store
            .add_nodes(
                0,
                (0..257)
                    .map(|id| (id.to_string(), Properties::new()))
                    .collect(),
            )
            .unwrap();
        let mut edges = Vec::new();
        for &node in &nodes {
            edges.push((nodes[0], node, "out".into(), Properties::new()));
            edges.push((node, nodes[0], "in".into(), Properties::new()));
            edges.push((node, nodes[0], "second".into(), Properties::new()));
        }
        let ids = store.add_edges(edges).unwrap();
        for &id in ids.iter().step_by(3) {
            assert!(store.remove_edge(id));
        }
        assert_integrity(&store);
        store.remove_node(nodes[0]).unwrap();
        assert!(store.edges.is_empty());
        for node in &store.nodes {
            assert!(node.outgoing.is_empty() && node.incoming.is_empty());
        }
        assert_integrity(&store);
    }

    #[test]
    fn nested_scopes_allow_name_collisions_and_recursively_remove_cross_edges() {
        let mut store = Store::default();
        let root = add(&mut store, 0, &["company", "same", "outside"]);
        let child_scope = store.create_scope(root[0]).unwrap();
        assert_eq!(store.create_scope(root[0]).unwrap(), child_scope);
        let child = add(&mut store, child_scope, &["same", "department"]);
        let grand_scope = store.create_scope(child[1]).unwrap();
        let grand = add(&mut store, grand_scope, &["same"])[0];
        store.create_index(child_scope, "p".into()).unwrap();
        assert_eq!(store.scopes[&0].names["same"], root[1]);
        assert_eq!(store.scopes[&child_scope].names["same"], child[0]);
        assert_eq!(store.scopes[&grand_scope].names["same"], grand);
        let incoming = edge(&mut store, root[2], grand, "cross");
        let outgoing = edge(&mut store, child[0], root[2], "cross");
        let retained = edge(&mut store, root[1], root[2], "cross");
        assert_eq!(
            store
                .edge_ids(0, false, None, None, Some("cross"), &[])
                .unwrap(),
            [incoming, retained]
        );
        assert_eq!(
            store
                .edge_ids(child_scope, false, None, None, None, &[])
                .unwrap(),
            [outgoing]
        );
        assert_eq!(store.stats(child_scope, true).unwrap()["nodes"], 3);
        assert_eq!(store.stats(child_scope, true).unwrap()["edges"], 1);
        assert_eq!(
            store.node_ids(0, true).unwrap(),
            [root[0], root[1], root[2], child[0], child[1], grand]
        );
        store.clear_scope(child_scope).unwrap();
        assert_eq!(store.node(root[0]).unwrap().child_scope, Some(child_scope));
        assert!(store.scopes.contains_key(&child_scope));
        assert!(!store.scopes.contains_key(&grand_scope));
        assert!(store.scopes[&child_scope].indexes.contains_key("p"));
        assert_eq!(
            store.edge_ids(0, true, None, None, None, &[]).unwrap(),
            [retained]
        );
        assert!(!store.node_positions.contains_key(&grand));
        let replacement = add(&mut store, child_scope, &["same"])[0];
        assert!(replacement > grand);
        let replacement_scope = store.create_scope(replacement).unwrap();
        assert!(replacement_scope > grand_scope);
        store.remove_node(root[0]).unwrap();
        assert!(!store.scopes.contains_key(&child_scope));
        assert!(!store.scopes.contains_key(&replacement_scope));
        assert_eq!(store.node_ids(0, true).unwrap(), [root[1], root[2]]);
        assert_integrity(&store);
    }

    #[test]
    fn deep_scope_cleanup_is_iterative() {
        let mut store = Store::default();
        let first = add(&mut store, 0, &["owner"])[0];
        let mut owner = first;
        for _ in 0..512 {
            let scope = store.create_scope(owner).unwrap();
            owner = add(&mut store, scope, &["owner"])[0];
        }
        assert_eq!(store.node_ids(0, true).unwrap().len(), 513);
        assert_eq!(
            store
                .bfs(first, &options("out", true), None)
                .unwrap()
                .depths
                .last(),
            Some(&512)
        );
        store.remove_node(first).unwrap();
        assert_eq!(store.scopes.len(), 1);
        assert!(store.nodes.is_empty());
        assert_integrity(&store);
    }

    #[test]
    fn complete_batches_validate_before_any_properties_ids_or_revision_change() {
        let mut store = Store::default();
        let nodes = add(&mut store, 0, &["a", "b"]);
        store.create_index(0, "p".into()).unwrap();
        edge(&mut store, nodes[0], nodes[1], "r");
        let before = store.snapshot().unwrap();
        let bad_attrs = attrs(json!({"p": u64::MAX}));
        assert!(store
            .add_nodes(
                0,
                vec![
                    ("a".into(), attrs(json!({"p": "changed"}))),
                    ("new".into(), bad_attrs.clone())
                ]
            )
            .is_err());
        assert_eq!(store.snapshot().unwrap(), before);
        assert!(store
            .add_edges(vec![
                (
                    nodes[0],
                    nodes[1],
                    "r".into(),
                    attrs(json!({"changed": true}))
                ),
                (nodes[0], u32::MAX, "new_relation".into(), Properties::new()),
            ])
            .is_err());
        assert_eq!(store.snapshot().unwrap(), before);
        assert!(store
            .add_edges(vec![
                (
                    nodes[0],
                    nodes[1],
                    "r".into(),
                    attrs(json!({"changed": true}))
                ),
                (nodes[1], nodes[0], "new_relation".into(), bad_attrs),
            ])
            .is_err());
        assert_eq!(store.snapshot().unwrap(), before);
        assert!(!store.relation_ids.contains_key("new_relation"));
        assert!(store
            .add_nodes(999, vec![("new".into(), Properties::new())])
            .is_err());
        store.next_node_id = ID_LIMIT;
        let exhausted = store.snapshot().unwrap();
        assert!(store
            .add_nodes(
                0,
                vec![
                    ("a".into(), attrs(json!({"p": "changed"}))),
                    ("new".into(), Properties::new())
                ]
            )
            .is_err());
        assert_eq!(store.snapshot().unwrap(), exhausted);
        assert_integrity(&store);
    }

    #[test]
    fn null_missing_typed_equality_and_batch_index_updates_agree_with_full_scan() {
        let mut store = Store::default();
        let ids = store
            .add_nodes(
                0,
                vec![
                    ("missing".into(), Properties::new()),
                    ("null".into(), attrs(json!({"p": null}))),
                    ("bool".into(), attrs(json!({"p": true}))),
                    ("int".into(), attrs(json!({"p": 1}))),
                    ("float".into(), attrs(json!({"p": 1.0}))),
                    ("list".into(), attrs(json!({"p": [1, true, null]}))),
                    ("dict".into(), attrs(json!({"p": {"a": 1, "b": true}}))),
                ],
            )
            .unwrap();
        let values = [
            json!(null),
            json!(true),
            json!(1),
            json!(1.0),
            json!([1, true, null]),
            json!({"b": true, "a": 1}),
        ];
        let scans: Vec<_> = values
            .iter()
            .map(|value| find(&store, 0, "p", "eq", value.clone()))
            .collect();
        assert_eq!(
            scans,
            ids[1..].iter().map(|&id| vec![id]).collect::<Vec<_>>()
        );
        store.create_index(0, "p".into()).unwrap();
        for (value, expected) in values.into_iter().zip(scans) {
            assert_eq!(find(&store, 0, "p", "eq", value), expected);
        }
        assert_eq!(find(&store, 0, "p", "exists", json!(false)), [ids[0]]);
        assert!(!find(&store, 0, "p", "ne", json!(null)).contains(&ids[0]));
        store
            .add_nodes(
                0,
                vec![
                    ("null".into(), attrs(json!({"p": "old"}))),
                    ("null".into(), attrs(json!({"p": "new"}))),
                    ("int".into(), Properties::new()),
                    ("missing".into(), attrs(json!({"p": null}))),
                ],
            )
            .unwrap();
        assert!(find(&store, 0, "p", "eq", json!("old")).is_empty());
        assert_eq!(find(&store, 0, "p", "eq", json!("new")), [ids[1]]);
        assert_eq!(find(&store, 0, "p", "eq", json!(null)), [ids[0]]);
        assert_eq!(find(&store, 0, "p", "exists", json!(false)), [ids[3]]);
        assert_integrity(&store);
        store.drop_index(0, "p").unwrap();
        assert_eq!(find(&store, 0, "p", "eq", json!(null)), [ids[0]]);
    }

    #[test]
    fn numeric_ranges_preserve_large_integer_precision_and_other_operators_are_typed() {
        let mut store = Store::default();
        let ids = store
            .add_nodes(
                0,
                vec![
                    (
                        "large".into(),
                        attrs(json!({"p": 9_007_199_254_740_993i64})),
                    ),
                    ("float".into(), attrs(json!({"p": 9_007_199_254_740_992.0}))),
                    ("max".into(), attrs(json!({"p": i64::MAX}))),
                    ("min".into(), attrs(json!({"p": i64::MIN}))),
                    ("bool".into(), attrs(json!({"p": true}))),
                    ("list".into(), attrs(json!({"p": [1, true]}))),
                    ("text".into(), attrs(json!({"p": "alphabet"}))),
                    ("dict".into(), attrs(json!({"p": {"key": null}}))),
                ],
            )
            .unwrap();
        assert_eq!(
            find(&store, 0, "p", "gt", json!(9_007_199_254_740_992.0)),
            [ids[0], ids[2]]
        );
        assert_eq!(
            find(&store, 0, "p", "lt", json!(9_223_372_036_854_775_808.0)),
            ids[..4]
        );
        assert_eq!(
            find(&store, 0, "p", "lte", json!(-9_223_372_036_854_775_808.0)),
            [ids[3]]
        );
        assert_eq!(
            find(&store, 0, "p", "gte", json!(9_007_199_254_740_993i64)),
            [ids[0], ids[2]]
        );
        assert_eq!(
            find(&store, 0, "p", "in", json!([true, "alphabet"])),
            [ids[4], ids[6]]
        );
        assert_eq!(find(&store, 0, "p", "contains", json!(true)), [ids[5]]);
        assert!(find(&store, 0, "p", "contains", json!(1.0)).is_empty());
        assert_eq!(find(&store, 0, "p", "contains", json!("key")), [ids[7]]);
        assert_eq!(find(&store, 0, "p", "contains", json!("pha")), [ids[6]]);
        assert_eq!(find(&store, 0, "p", "startswith", json!("alpha")), [ids[6]]);
        assert!(Filter::new("p".into(), "exists", json!(1)).is_err());
        assert!(Filter::new("p".into(), "in", json!("alphabet")).is_err());
        assert!(Filter::new("p".into(), "unknown", json!(null)).is_err());
        assert_eq!(compare_int_float(-1, -1.5), Ordering::Greater);
        assert_eq!(compare_int_float(0, 0.5), Ordering::Less);
        assert_eq!(compare_int_float(i64::MIN, -f64::MAX), Ordering::Greater);
    }

    #[test]
    fn all_edge_predicates_intersect_and_scope_is_always_source_owned() {
        let mut store = Store::default();
        let root = add(&mut store, 0, &["owner", "a", "b"]);
        let scope = store.create_scope(root[0]).unwrap();
        let child = add(&mut store, scope, &["a", "b"]);
        let ids = store
            .add_edges(vec![
                (root[1], root[2], "r".into(), attrs(json!({"p": 1}))),
                (root[1], child[1], "r".into(), attrs(json!({"p": 2}))),
                (child[0], root[2], "r".into(), attrs(json!({"p": 3}))),
                (child[0], child[1], "r".into(), attrs(json!({"p": 4}))),
                (root[1], root[2], "other".into(), attrs(json!({"p": 5}))),
            ])
            .unwrap();
        assert_eq!(
            store
                .edge_ids(0, false, Some(root[1]), Some(root[2]), Some("r"), &[])
                .unwrap(),
            [ids[0]]
        );
        assert_eq!(
            store
                .edge_ids(0, false, None, Some(root[2]), Some("r"), &[])
                .unwrap(),
            [ids[0]]
        );
        assert_eq!(
            store
                .edge_ids(0, true, None, Some(root[2]), Some("r"), &[])
                .unwrap(),
            [ids[0], ids[2]]
        );
        assert!(store
            .edge_ids(scope, false, Some(root[1]), None, Some("r"), &[])
            .unwrap()
            .is_empty());
        assert_eq!(
            store
                .edge_ids(
                    0,
                    true,
                    None,
                    None,
                    Some("r"),
                    &[filter("p", "gte", json!(3))]
                )
                .unwrap(),
            [ids[2], ids[3]]
        );
        assert!(store
            .edge_ids(0, true, None, None, Some("missing"), &[])
            .unwrap()
            .is_empty());
        assert!(store
            .edge_ids(0, true, Some(u32::MAX), None, None, &[])
            .unwrap()
            .is_empty());
        assert_integrity(&store);
    }

    #[test]
    fn local_edge_batches_are_atomic_upserts_with_scope_specific_endpoints() {
        let mut store = Store::default();
        let root = add(&mut store, 0, &["a", "b", "owner"]);
        let scope = store.create_scope(root[2]).unwrap();
        let child = add(&mut store, scope, &["a", "b"]);
        let root_edge = store
            .add_edges_local(
                0,
                vec![("a".into(), "b".into(), "r".into(), attrs(json!({"p": 1})))],
            )
            .unwrap()[0];
        let child_edge = store
            .add_edges_local(
                scope,
                vec![
                    ("a".into(), "b".into(), "r".into(), attrs(json!({"p": 2}))),
                    ("a".into(), "b".into(), "r".into(), attrs(json!({"p": 3}))),
                ],
            )
            .unwrap();
        assert_eq!(child_edge[0], child_edge[1]);
        assert_ne!(root_edge, child_edge[0]);
        assert_eq!(
            store.edge_local_id(0, "a", "b", "r").unwrap(),
            Some(root_edge)
        );
        assert_eq!(store.edge(child_edge[0]).unwrap().src, child[0]);
        assert_eq!(store.edge(child_edge[0]).unwrap().dst, child[1]);
        assert_eq!(
            store.edge(child_edge[0]).unwrap().attrs,
            attrs(json!({"p": 3}))
        );
        let before = store.snapshot().unwrap();
        assert!(store
            .add_edges_local(
                scope,
                vec![
                    (
                        "a".into(),
                        "b".into(),
                        "r".into(),
                        attrs(json!({"changed": true}))
                    ),
                    (
                        "a".into(),
                        "missing".into(),
                        "new".into(),
                        Properties::new()
                    ),
                ]
            )
            .is_err());
        assert_eq!(store.snapshot().unwrap(), before);
        assert!(store
            .add_edges_local(
                0,
                vec![
                    (
                        "a".into(),
                        "b".into(),
                        "r".into(),
                        attrs(json!({"changed": true}))
                    ),
                    (
                        "b".into(),
                        "a".into(),
                        "new".into(),
                        attrs(json!({"bad": u64::MAX}))
                    ),
                ]
            )
            .is_err());
        assert_eq!(store.snapshot().unwrap(), before);
        assert_integrity(&store);
    }

    #[test]
    fn recursive_index_queries_and_limits_keep_allocation_order() {
        let mut store = Store::default();
        let owner = add(&mut store, 0, &["owner"])[0];
        let scope = store.create_scope(owner).unwrap();
        let child = store
            .add_nodes(scope, vec![("first".into(), attrs(json!({"p": 1})))])
            .unwrap()[0];
        let root = store
            .add_nodes(0, vec![("later".into(), attrs(json!({"p": 1})))])
            .unwrap()[0];
        let second = store
            .add_nodes(scope, vec![("second".into(), attrs(json!({"p": 1})))])
            .unwrap()[0];
        store.create_index(0, "p".into()).unwrap();
        store.create_index(scope, "p".into()).unwrap();
        let filters = [filter("p", "eq", json!(1))];
        assert_eq!(
            store.find_nodes(0, &filters, true, None).unwrap(),
            [child, root, second]
        );
        assert_eq!(
            store.find_nodes(0, &filters, true, Some(2)).unwrap(),
            [child, root]
        );
        assert!(store
            .find_nodes(0, &filters, true, Some(0))
            .unwrap()
            .is_empty());
        assert_eq!(
            store.find_nodes(scope, &filters, false, Some(1)).unwrap(),
            [child]
        );
        assert_integrity(&store);
    }

    #[test]
    fn bfs_is_directed_bounded_and_stores_only_predecessors() {
        let mut store = Store::default();
        let nodes = add(&mut store, 0, &["s", "a", "b", "t", "isolated"]);
        let ids = store
            .add_edges(vec![
                (nodes[0], nodes[1], "r".into(), Properties::new()),
                (nodes[0], nodes[2], "r".into(), Properties::new()),
                (nodes[1], nodes[3], "r".into(), Properties::new()),
                (nodes[2], nodes[3], "r".into(), Properties::new()),
            ])
            .unwrap();
        let result = store.bfs(nodes[0], &options("out", false), None).unwrap();
        assert_eq!(result.nodes, nodes[..4]);
        assert_eq!(
            result.parents,
            [None, Some(nodes[0]), Some(nodes[0]), Some(nodes[1])]
        );
        assert_eq!(result.depths, [0, 1, 1, 2]);
        assert_eq!(
            result.tree_edges,
            [None, Some(ids[0]), Some(ids[1]), Some(ids[2])]
        );
        assert_eq!(
            store
                .shortest_path(nodes[0], nodes[3], &options("out", false))
                .unwrap(),
            Some(vec![nodes[0], nodes[1], nodes[3]])
        );
        assert_eq!(
            store
                .shortest_path(nodes[3], nodes[0], &options("out", false))
                .unwrap(),
            None
        );
        assert_eq!(
            store
                .shortest_path(nodes[3], nodes[0], &options("in", false))
                .unwrap(),
            Some(vec![nodes[3], nodes[1], nodes[0]])
        );
        assert_eq!(
            store
                .shortest_path(nodes[0], nodes[0], &options("out", false))
                .unwrap(),
            Some(vec![nodes[0]])
        );
        let bounded = bfs_options(Some(1), "out", None, false, None, None).unwrap();
        assert_eq!(
            store.bfs(nodes[0], &bounded, None).unwrap().nodes,
            nodes[..3]
        );
        assert_eq!(
            store.shortest_path(nodes[0], nodes[3], &bounded).unwrap(),
            None
        );
        let allowed = bfs_options(
            None,
            "out",
            None,
            false,
            Some(2),
            Some(vec![nodes[2], nodes[3]]),
        )
        .unwrap();
        assert_eq!(
            store.bfs(nodes[0], &allowed, None).unwrap().nodes,
            [nodes[0], nodes[2]]
        );
        assert_eq!(
            store
                .bfs(
                    nodes[0],
                    &bfs_options(Some(0), "out", None, false, None, None).unwrap(),
                    None
                )
                .unwrap()
                .nodes,
            [nodes[0]]
        );
        assert!(bfs_options(Some(-1), "out", None, false, None, None).is_err());
        assert!(bfs_options(None, "out", None, false, Some(0), None).is_err());
        assert!(bfs_options(None, "sideways", None, false, None, None).is_err());
        assert!(store
            .shortest_path(nodes[0], u32::MAX, &options("out", false))
            .is_err());
    }

    #[test]
    fn containment_hops_ignore_relation_filters_but_respect_direction_and_depth() {
        let mut store = Store::default();
        let root = add(&mut store, 0, &["owner", "outside"]);
        let scope = store.create_scope(root[0]).unwrap();
        let children = add(&mut store, scope, &["child", "compound"]);
        let grand_scope = store.create_scope(children[1]).unwrap();
        let grandchild = add(&mut store, grand_scope, &["grandchild"])[0];
        edge(&mut store, children[0], root[1], "explicit");
        let filtered =
            bfs_options(None, "out", Some("not_interned".into()), true, None, None).unwrap();
        let result = store.bfs(root[0], &filtered, None).unwrap();
        assert_eq!(
            result.nodes,
            [root[0], children[0], children[1], grandchild]
        );
        assert_eq!(
            result.parents,
            [None, Some(root[0]), Some(root[0]), Some(children[1])]
        );
        assert_eq!(result.depths, [0, 1, 1, 2]);
        assert_eq!(result.tree_edges, [None, None, None, None]);
        assert_eq!(
            store
                .bfs(grandchild, &options("out", true), None)
                .unwrap()
                .nodes,
            [grandchild]
        );
        assert_eq!(
            store
                .bfs(grandchild, &options("in", true), None)
                .unwrap()
                .nodes,
            [grandchild, children[1], root[0]]
        );
        assert_eq!(
            store.shortest_path(root[0], grandchild, &filtered).unwrap(),
            Some(vec![root[0], children[1], grandchild])
        );
        let direct = bfs_options(Some(1), "out", None, true, None, None).unwrap();
        assert_eq!(
            store.bfs(root[0], &direct, None).unwrap().nodes,
            [root[0], children[0], children[1]]
        );
        assert_eq!(
            store
                .bfs(root[0], &options("out", false), None)
                .unwrap()
                .nodes,
            [root[0]]
        );
        let both = store.bfs(grandchild, &options("both", true), None).unwrap();
        assert!(both.nodes.contains(&children[0]));
        assert!(both.nodes.contains(&root[1]));
    }

    #[test]
    fn long_chain_bfs_retains_one_parent_per_node() {
        let mut store = Store::default();
        let ids = store
            .add_nodes(
                0,
                (0..4096)
                    .map(|id| (id.to_string(), Properties::new()))
                    .collect(),
            )
            .unwrap();
        store
            .add_edges(
                ids.windows(2)
                    .map(|pair| (pair[0], pair[1], "r".into(), Properties::new()))
                    .collect(),
            )
            .unwrap();
        let result = store.bfs(ids[0], &options("out", false), None).unwrap();
        assert_eq!(result.nodes, ids);
        assert_eq!(result.parents.len(), 4096);
        assert_eq!(result.tree_edges.len(), 4096);
        assert_eq!(result.positions.len(), 4096);
        assert_eq!(result.depths.last(), Some(&4095));
        assert_eq!(
            store
                .shortest_path(ids[0], ids[4095], &options("out", false))
                .unwrap()
                .unwrap(),
            ids
        );
    }

    #[test]
    fn weak_components_and_topology_ignore_outside_members_and_detect_cycles() {
        let mut store = Store::default();
        let nodes = add(&mut store, 0, &["s", "a", "b", "isolated", "owner"]);
        let scope = store.create_scope(nodes[4]).unwrap();
        let outside = add(&mut store, scope, &["outside"])[0];
        edge(&mut store, nodes[0], nodes[1], "r");
        edge(&mut store, nodes[0], nodes[1], "r");
        edge(&mut store, nodes[1], nodes[2], "r");
        edge(&mut store, nodes[2], outside, "cross");
        edge(&mut store, outside, nodes[0], "cross");
        assert_eq!(
            store.connected_components(0, false).unwrap(),
            [
                vec![nodes[0], nodes[1], nodes[2]],
                vec![nodes[3]],
                vec![nodes[4]]
            ]
        );
        assert_eq!(
            store.topological_sort(0, false).unwrap(),
            Some(nodes.clone())
        );
        assert_eq!(store.topological_sort(0, true).unwrap(), None);
        let back = edge(&mut store, nodes[2], nodes[1], "r");
        assert_eq!(store.topological_sort(0, false).unwrap(), None);
        store.remove_edges(vec![back]).unwrap();
        assert!(store.topological_sort(0, false).unwrap().is_some());
        let self_loop = edge(&mut store, nodes[3], nodes[3], "r");
        assert!(store.topological_sort(0, false).unwrap().is_none());
        store.remove_edges(vec![self_loop]).unwrap();
        store.clear_scope(0).unwrap();
        assert!(store.connected_components(0, true).unwrap().is_empty());
        assert_eq!(store.topological_sort(0, true).unwrap(), Some(Vec::new()));
        assert_integrity(&store);
    }

    #[test]
    fn snapshot_roundtrip_preserves_ids_high_watermarks_index_definitions_and_independent_clone() {
        let mut store = Store::default();
        let ids = store
            .add_nodes(
                0,
                vec![
                    (
                        "owner".into(),
                        attrs(json!({"p": true, "min": i64::MIN, "max": i64::MAX})),
                    ),
                    ("removed".into(), Properties::new()),
                ],
            )
            .unwrap();
        let scope = store.create_scope(ids[0]).unwrap();
        let child = store
            .add_nodes(
                scope,
                vec![(
                    "same".into(),
                    attrs(json!({"p": 1.0, "nested": [{"null": null}]})),
                )],
            )
            .unwrap()[0];
        store.create_index(0, "p".into()).unwrap();
        store.create_index(scope, "p".into()).unwrap();
        let retained = edge(&mut store, child, ids[0], "cross");
        let removed_edge = edge(&mut store, ids[0], ids[1], "r");
        store.remove_node(ids[1]).unwrap();
        let data = store.snapshot().unwrap();
        let parsed: Value = serde_json::from_slice(&data).unwrap();
        assert!(parsed["scopes"][0].get("postings").is_none());
        let mut loaded = Store::from_snapshot(&data).unwrap();
        assert_eq!(loaded.snapshot().unwrap(), data);
        assert_eq!(loaded.revision, store.revision);
        assert_eq!(loaded.edge(retained).unwrap().src, child);
        assert_eq!(find(&loaded, scope, "p", "eq", json!(1.0)), [child]);
        loaded
            .add_nodes(scope, vec![("same".into(), attrs(json!({"p": null})))])
            .unwrap();
        assert!(find(&loaded, scope, "p", "eq", json!(1.0)).is_empty());
        assert_eq!(find(&loaded, scope, "p", "eq", json!(null)), [child]);
        let future = add(&mut loaded, 0, &["removed"])[0];
        assert!(future > child && future > ids[1]);
        assert!(edge(&mut loaded, ids[0], future, "r") > removed_edge);
        assert_eq!(store.snapshot().unwrap(), data);
        let mut cloned = loaded.clone();
        cloned.clear_scope(0).unwrap();
        assert!(!loaded.nodes.is_empty());
        assert!(cloned.nodes.is_empty());
        assert_integrity(&loaded);
        assert_integrity(&cloned);
    }

    #[test]
    fn snapshot_rejects_invalid_schema_references_duplicates_and_hierarchy() {
        let mut store = Store::default();
        let ids = add(&mut store, 0, &["owner", "b"]);
        let scope = store.create_scope(ids[0]).unwrap();
        add(&mut store, scope, &["child"]);
        edge(&mut store, ids[0], ids[1], "r");
        store.create_index(0, "p".into()).unwrap();
        let original: Value = serde_json::from_slice(&store.snapshot().unwrap()).unwrap();
        let reject = |value: Value| {
            assert!(Store::from_snapshot(&serde_json::to_vec(&value).unwrap()).is_err());
        };
        let mut bad = original.clone();
        bad["version"] = json!(99);
        reject(bad);
        let mut bad = original.clone();
        bad["unknown"] = json!(true);
        reject(bad);
        let mut bad = original.clone();
        bad["next_node_id"] = json!(0);
        reject(bad);
        let mut bad = original.clone();
        bad["next_scope_id"] = json!(0);
        reject(bad);
        let mut bad = original.clone();
        bad["next_edge_id"] = json!(0);
        reject(bad);
        let mut bad = original.clone();
        bad["edges"][0]["dst"] = json!(99999);
        reject(bad);
        let mut bad = original.clone();
        bad["nodes"][0]["child_scope"] = json!(0);
        reject(bad);
        let mut bad = original.clone();
        bad["nodes"][0]["scope"] = json!(99999);
        reject(bad);
        let mut bad = original.clone();
        bad["scopes"][0]["owner"] = json!(ids[0]);
        reject(bad);
        let mut bad = original.clone();
        bad["scopes"][1]["owner"] = json!(ids[1]);
        reject(bad);
        let mut bad = original.clone();
        bad["scopes"].as_array_mut().unwrap().remove(0);
        reject(bad);
        let mut bad = original.clone();
        let duplicate = bad["nodes"][0].clone();
        bad["nodes"].as_array_mut().unwrap().push(duplicate);
        reject(bad);
        let mut bad = original.clone();
        bad["nodes"][1]["local_id"] = json!("owner");
        reject(bad);
        let mut bad = original.clone();
        let duplicate = bad["edges"][0].clone();
        bad["edges"].as_array_mut().unwrap().push(duplicate);
        reject(bad);
        let mut bad = original.clone();
        let mut duplicate = bad["edges"][0].clone();
        duplicate["id"] = json!(1);
        bad["next_edge_id"] = json!(2);
        bad["edges"].as_array_mut().unwrap().push(duplicate);
        reject(bad);
        let mut bad = original.clone();
        bad["scopes"][0]["indexes"] = json!(["p", "p"]);
        reject(bad);
        let mut bad = original.clone();
        bad["nodes"][0]["attrs"] = json!([]);
        reject(bad);
        let cycle = json!({
            "version": 1, "revision": 0, "next_node_id": 2, "next_scope_id": 3, "next_edge_id": 0,
            "scopes": [{"id": 0, "owner": null, "indexes": []}, {"id": 1, "owner": 0, "indexes": []}, {"id": 2, "owner": 1, "indexes": []}],
            "nodes": [{"id": 0, "scope": 2, "local_id": "a", "child_scope": 1, "attrs": {}}, {"id": 1, "scope": 1, "local_id": "b", "child_scope": 2, "attrs": {}}],
            "edges": [],
        });
        reject(cycle);
        assert!(Store::from_snapshot(b"not JSON").is_err());
        assert!(Store::from_snapshot(b"\xff").is_err());
        let mut trailing = store.snapshot().unwrap();
        trailing.extend(b" null");
        assert!(Store::from_snapshot(&trailing).is_err());
        assert_integrity(&store);
    }

    #[test]
    fn snapshot_strictly_validates_nested_property_numbers_and_duplicate_keys() {
        let mut store = Store::default();
        store
            .add_nodes(0, vec![("n".into(), attrs(json!({"p": "REPLACE"})))])
            .unwrap();
        let base = String::from_utf8(store.snapshot().unwrap()).unwrap();
        for literal in [
            "9223372036854775808",
            "-9223372036854775809",
            "18446744073709551616",
            "1e400",
            "NaN",
            "Infinity",
            "{\"a\":1,\"a\":2}",
            "{\"nested\":{\"a\":1,\"a\":2}}",
        ] {
            let data = base.replace("\"REPLACE\"", literal);
            assert!(
                Store::from_snapshot(data.as_bytes()).is_err(),
                "accepted {literal}"
            );
        }
        for literal in [
            "9223372036854775807",
            "-9223372036854775808",
            "1.0",
            "true",
            "null",
            "{\"$serde_json::private::Number\":\"text\"}",
        ] {
            let data = base.replace("\"REPLACE\"", literal);
            let loaded = Store::from_snapshot(data.as_bytes()).unwrap();
            assert_integrity(&loaded);
        }
        for (literal, is_integer) in [("-0", true), ("-0.0", false), ("-0e0", false)] {
            let data = base.replace("\"REPLACE\"", literal);
            let loaded = Store::from_snapshot(data.as_bytes()).unwrap();
            let value = loaded.nodes[0].attrs.get("p").unwrap();
            assert_eq!(value.as_number().unwrap().is_i64(), is_integer);
        }
        let duplicate = base.replacen("\"version\":1", "\"version\":1,\"version\":1", 1);
        assert!(Store::from_snapshot(duplicate.as_bytes()).is_err());
    }

    #[test]
    fn high_watermarks_do_not_allocate_sparse_vectors_or_alias_removed_handles() {
        let mut store = Store {
            next_node_id: u32::MAX as u64,
            next_edge_id: u32::MAX as u64,
            next_scope_id: u32::MAX as u64,
            ..Store::default()
        };
        let node = add(&mut store, 0, &["last"])[0];
        assert_eq!(node, u32::MAX);
        let scope = store.create_scope(node).unwrap();
        assert_eq!(scope, u32::MAX);
        assert_eq!(edge(&mut store, node, node, "r"), u32::MAX);
        assert!(store
            .add_nodes(0, vec![("exhausted".into(), Properties::new())])
            .is_err());
        let loaded = Store::from_snapshot(&store.snapshot().unwrap()).unwrap();
        assert_eq!(loaded.nodes.len(), 1);
        assert_eq!(loaded.edges.len(), 1);
        assert!(loaded.memory_usage()["total_bytes"] < 100_000);
        store.remove_node(node).unwrap();
        let mut empty = Store::from_snapshot(&store.snapshot().unwrap()).unwrap();
        assert!(!empty.node_positions.contains_key(&node));
        assert!(!empty.scopes.contains_key(&scope));
        assert!(empty
            .add_nodes(0, vec![("last".into(), Properties::new())])
            .is_err());
        assert_integrity(&empty);
    }

    #[test]
    fn memory_estimates_include_properties_indexes_and_retained_capacities() {
        let mut store = Store::default();
        let ids = add(&mut store, 0, &["a", "b"]);
        let before = store.memory_usage();
        let blob = "x".repeat(100_000);
        store
            .add_edges(vec![(
                ids[0],
                ids[1],
                "r".into(),
                attrs(json!({"blob": blob})),
            )])
            .unwrap();
        let with_edge = store.memory_usage();
        assert!(with_edge["properties_bytes"] >= before["properties_bytes"] + 100_000);
        store
            .add_nodes(0, vec![("a".into(), attrs(json!({"p": "value"})))])
            .unwrap();
        store.create_index(0, "p".into()).unwrap();
        let indexed = store.memory_usage();
        assert!(indexed["indexes_bytes"] > with_edge["indexes_bytes"]);
        assert_eq!(
            indexed["total_bytes"],
            indexed["nodes_bytes"]
                + indexed["edges_bytes"]
                + indexed["indexes_bytes"]
                + indexed["properties_bytes"]
        );
        store.clear_scope(0).unwrap();
        let cleared = store.memory_usage();
        assert!(cleared["properties_bytes"] < indexed["properties_bytes"]);
        assert!(cleared["nodes_bytes"] > 0 && cleared["edges_bytes"] > 0);
    }

    #[test]
    fn python_boundary_keyword_contract_copies_properties_and_rejects_non_json_atomically() {
        Python::attach(|py| {
            let locals = PyDict::new(py);
            locals
                .set_item("NativeStore", py.get_type::<NativeStore>())
                .unwrap();
            let script = CString::new(r#"
import gc
import weakref

store = NativeStore()
assert store.revision == 0
assert store.scope_owner(scope=0) is None
payload = {"nested": {"values": [None, True, 1, 1.0]}, "min": -(2**63), "max": 2**63 - 1}
a, b = store.add_nodes(scope=0, nodes=[("a", payload), ("b", {})])
payload["nested"]["values"].append("external")
copied = store.get_node(node=a)
assert copied["nested"]["values"] == [None, True, 1, 1.0]
assert type(copied["nested"]["values"][1]) is bool
assert type(copied["nested"]["values"][2]) is int
assert type(copied["nested"]["values"][3]) is float
copied["nested"]["values"].clear()
assert len(store.get_node(a)["nested"]["values"]) == 4
child_scope = store.create_scope(owner=a)
child, = store.add_nodes(scope=child_scope, nodes=[("a", {"p": None})])
assert store.node_info(node=child) == (child_scope, "a", None)
assert store.node_id(scope=0, local_id="a") == a
assert store.node_ids(scope=0, recursive=True) == [a, b, child]
store.create_index(scope=child_scope, property="p")
assert store.index_names(scope=child_scope) == ["p"]
assert store.find_nodes(scope=child_scope, filters=[("p", "eq", None)], limit=1) == [child]
edge, = store.add_edges(edges=[(a, b, "r", {"weight": 1.0})])
assert store.edge_id(src=a, dst=b, rel="r") == edge
assert store.edge_local(scope=0, src="a", dst="b", rel="r") == (edge, {"weight": 1.0})
assert store.has_edge_local(scope=0, src="a", dst="b", rel="r") is True
assert store.has_edge_local(scope=child_scope, src="a", dst="b", rel="r") is False
assert store.edge_local(scope=0, src="missing", dst="b", rel="r") is None
local_attrs = store.edge_local(0, "a", "b", "r")[1]
local_attrs["weight"] = 2.0
assert store.edge_local(0, "a", "b", "r")[1] == {"weight": 1.0}
assert store.add_edges_local(scope=0, edges=[("a", "b", "r", {"weight": 1.0})]) == [edge]
assert store.edge_ids(scope=0, src=a, dst=b, rel="r", filters=[("weight", "eq", 1.0)]) == [edge]
assert store.edge_ids(scope=0, src=a, dst=child, rel="r") == []
assert store.get_edge(edge=edge) == (a, b, "r", {"weight": 1.0})
assert store.neighbors(node=a, direction="out", rel="r") == [(b, edge)]
assert store.degree(node=a) == (1, 0)
assert store.bfs(start=a, max_depth=1, direction="out", rel="missing", nested=True, max_nodes=2, allowed=[child]) == ([a, child], [None, a], [0, 1], [None, None])
assert store.shortest_path(start=a, end=child, direction="out", nested=True, max_depth=1) == [a, child]
assert store.shortest_path(start=b, end=a) is None
before = store.snapshot()
cycle = []
cycle.append(cycle)
for bad in [2**63, -(2**63)-1, float("nan"), float("inf"), float("-inf"), b"bytes", (1, 2), {1}, object(), {1: "key"}, cycle]:
    try:
        store.add_nodes(scope=0, nodes=[("a", {"changed": True}), ("bad", {"p": bad})])
    except ValueError:
        pass
    else:
        raise AssertionError("accepted unsupported property")
    assert store.snapshot() == before
try:
    store.add_edges([(a, b, "r", {"changed": True}), (a, 999999, "r", {})])
except KeyError:
    pass
else:
    raise AssertionError("accepted absent endpoint")
assert store.snapshot() == before
try:
    store.add_edges_local(scope=0, edges=[("a", "b", "r", {"changed": True}), ("a", "missing", "r", {})])
except KeyError:
    pass
else:
    raise AssertionError("accepted absent local endpoint")
assert store.snapshot() == before
for args in [{"max_depth": -1}, {"max_nodes": 0}, {"direction": "invalid"}]:
    try:
        store.bfs(a, **args)
    except ValueError:
        pass
    else:
        raise AssertionError("accepted invalid traversal budget")
loaded = NativeStore.from_snapshot(data=before)
assert loaded.snapshot() == before
clone = store.clone()
clone.clear_scope(scope=0)
assert store.snapshot() == before
assert clone.node_ids(0, recursive=True) == []
class TrackedList(list):
    pass
tracked = TrackedList([1, None])
reference = weakref.ref(tracked)
store.add_nodes(0, [("tracked", {"p": tracked})])
del tracked
gc.collect()
assert reference() is None
assert store.stats(scope=0, recursive=True)["nodes"] == 4
assert store.memory_usage()["total_bytes"] > 0
assert store.remove_edges(edges=[edge, edge, 999999]) == 1
assert store.remove_node(node=a) is True
assert not store.has_node(node=child)
assert not store.scope_exists(scope=child_scope)
assert store.remove_node(node=a) is False
assert store.connected_components(scope=0) == [[b], [store.node_id(0, "tracked")]]
assert store.topological_sort(scope=0) == [b, store.node_id(0, "tracked")]
store.drop_index(scope=0, property="absent")
"#).unwrap();
            py.run(&script, Some(&locals), None).unwrap();
        });
    }

    #[test]
    fn native_rwlock_supports_parallel_snapshot_readers_and_atomic_batch_writers() {
        let store = Arc::new(RwLock::new(Store::default()));
        let mut threads = Vec::new();
        for worker in 0..4 {
            let store = Arc::clone(&store);
            threads.push(std::thread::spawn(move || {
                for batch in 0..32 {
                    let nodes = (0..4)
                        .map(|offset| {
                            (
                                format!("{worker}:{batch}:{offset}"),
                                attrs(json!({"worker": worker})),
                            )
                        })
                        .collect();
                    store.write().unwrap().add_nodes(0, nodes).unwrap();
                }
            }));
        }
        for _ in 0..2 {
            let store = Arc::clone(&store);
            threads.push(std::thread::spawn(move || {
                for _ in 0..32 {
                    let snapshot = store.read().unwrap().snapshot().unwrap();
                    let loaded = Store::from_snapshot(&snapshot).unwrap();
                    assert_eq!(loaded.nodes.len() % 4, 0);
                    assert_integrity(&loaded);
                }
            }));
        }
        for thread in threads {
            thread.join().unwrap();
        }
        let store = store.read().unwrap();
        assert_eq!(store.nodes.len(), 512);
        assert_eq!(store.revision, 128);
        assert_integrity(&store);
    }

    #[test]
    fn deterministic_mixed_mutations_preserve_adjacency_and_index_invariants() {
        let mut store = Store::default();
        store.create_index(0, "p".into()).unwrap();
        let mut seed = 0x243f_6a88u64;
        for step in 0..600 {
            seed = seed.wrapping_mul(6_364_136_223_846_793_005).wrapping_add(1);
            let slot = (seed >> 32) % 25;
            let name = format!("node{slot}");
            match seed % 5 {
                0 | 1 => {
                    store
                        .add_nodes(0, vec![(name, attrs(json!({"p": slot % 3, "step": step})))])
                        .unwrap();
                }
                2 if store.nodes.len() >= 2 => {
                    let src = store.nodes[(seed as usize) % store.nodes.len()].id;
                    let dst = store.nodes[((seed >> 16) as usize) % store.nodes.len()].id;
                    store
                        .add_edges(vec![(
                            src,
                            dst,
                            format!("r{}", slot % 3),
                            attrs(json!({"p": slot})),
                        )])
                        .unwrap();
                }
                3 => {
                    if let Some(&id) = store.scopes[&0].names.get(&name) {
                        store.remove_node(id).unwrap();
                    }
                }
                4 if !store.edges.is_empty() => {
                    let id = store.edges[(seed as usize) % store.edges.len()].id;
                    store.remove_edges(vec![id, id]).unwrap();
                }
                _ => {}
            }
            assert_integrity(&store);
            if step % 37 == 0 {
                let data = store.snapshot().unwrap();
                store = Store::from_snapshot(&data).unwrap();
                assert_eq!(store.snapshot().unwrap(), data);
            }
        }
        assert_integrity(&store);
    }
}
