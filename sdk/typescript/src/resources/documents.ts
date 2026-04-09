/**
 * Documents resource — file upload for RAG pipelines.
 */
import { HttpClient } from "../http.js";
import type { DocumentUploadResult } from "../types.js";

export class DocumentsResource {
  constructor(private readonly http: HttpClient) {}

  /**
   * Upload a .txt file to be chunked and stored in a collection.
   *
   * @param collectionName - Target collection name.
   * @param file - A File, Blob, or Buffer containing the document content.
   * @param filename - Optional filename (defaults to "document.txt").
   * @returns DocumentUploadResult with document_id and chunks_created count.
   */
  async upload(
    collectionName: string,
    file: Blob | Buffer,
    filename = "document.txt",
    options?: { includeTiming?: boolean }
  ): Promise<DocumentUploadResult> {
    const fields: Record<string, string> = { collection_name: collectionName };
    if (options?.includeTiming) fields.include_timing = "true";
    return this.http.requestMultipart<DocumentUploadResult>(
      "/v1/documents/upload",
      fields,
      file,
      filename
    );
  }
}
