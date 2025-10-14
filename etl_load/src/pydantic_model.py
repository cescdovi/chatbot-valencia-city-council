from pydantic import BaseModel, Field, HttpUrl
from typing import List, Dict, Union, Any, Optional


class ProcedureModel(BaseModel):
    title: str = Field(..., description="Título del bloque de información (ej. 'Descripción', 'Legislación').")
    content: List[str] = Field(..., description="Contenido o lista de párrafos/puntos del bloque.")

class CategoryModel(BaseModel):
    category_name: str = Field(..., description="El nombre oficial de la categoría dentro del área.")
    category_url: HttpUrl = Field(..., description="URL absoluta de la página de la categoría.")
    procedures: List[ProcedureModel] = Field(default_factory=list, description="Lista de todos los bloques de información extraídos de la categoría.")

class AreaModel(BaseModel):
    area_title: str = Field(..., description="El nombre oficial del área de la Administración.")
    categories: List[CategoryModel]

class Areas(BaseModel):
    areas: List[AreaModel] = Field(..., description="Lista de diccionarios.")
