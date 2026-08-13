from typing import Annotated, Union
from pydantic import BaseModel, Field, TypeAdapter
from typing_extensions import Literal


class GemDownloadTask(BaseModel):
    type: Literal["GEM_DOWNLOAD"]
    gemId: str
    tenderId: int


class NonGemDownloadTask(BaseModel):
    type: Literal["NON_GEM_DOWNLOAD"]
    referenceNo: str
    tenderId: int | None = None


_TenderTasksMessage = Annotated[
    Union[GemDownloadTask, NonGemDownloadTask],
    Field(discriminator="type"),
]
tender_tasks_adapter: TypeAdapter = TypeAdapter(_TenderTasksMessage)


class TenderParsingMessage(BaseModel):
    type: Literal["GEM_PDF_PARSING"]
    referenceNo: str

class CostingAttachmentParsing(BaseModel):
    type:Literal["COSTING_ATTACHMENT_PARSING"]
    referenceNo: str
    file_link: str | None = None
    tenderId: int | None = None
    file_type: Literal["network", "external"] | None = None
    decrypted_fileId: str | None = None
    timestamp: int | None = None

class NonGemParsing(BaseModel):
    type:Literal["NON_GEM_BOQ_PARSING"]
    referenceNo: str
    file_link: str

_ParsingMessage = Annotated[
    Union[TenderParsingMessage, CostingAttachmentParsing,NonGemParsing],
    Field(discriminator="type"),
]
parsing_adapter = TypeAdapter(_ParsingMessage)




