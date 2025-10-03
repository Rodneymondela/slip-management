from functools import wraps
import os
from flask import send_from_directory, current_app, abort
from flask_login import current_user
from ...models.document import Document

def user_owns_document(f):
    """
    Decorator: verifies that the current user owns the document specified by 'doc_id'.
    It fetches the document and passes it to the wrapped function, aborting with a 404
    if the document is not found or not owned by the user.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        doc_id = kwargs.get("doc_id")
        if doc_id is None:
            return abort(404)  # Should not happen with correct routing

        # Fetch the document ensuring it belongs to the logged-in user
        doc = Document.query.filter_by(id=doc_id, user_id=current_user.id).first()

        if doc is None:
            # Use 404 to avoid leaking information about document existence
            return abort(404)

        # Pass the fetched document object to the route function
        kwargs['doc'] = doc
        return f(*args, **kwargs)
    return decorated_function

def serve_secure_file(file_path: str, user_id: int):
    """
    Serves a file from a non-public directory after verifying ownership. This function
    is designed to prevent unauthorized access and directory traversal attacks.
    - file_path: The relative path to the file from the instance folder
                 (e.g., 'uploads/uuid.pdf' or 'thumbs/uuid.jpg').
    - user_id: The ID of the user requesting the file.
    """
    # Verify that a document record exists for this file path and belongs to the user
    query = Document.query.filter_by(user_id=user_id)
    if 'thumbs/' in file_path:
        doc = query.filter_by(thumbnail_path=file_path).first()
    else:
        doc = query.filter_by(file_path=file_path).first()

    if not doc:
        # Abort if no record is found, preventing info leaks about file existence
        return abort(404)

    # Construct the full, absolute path to the file within the instance folder
    full_path = os.path.join(current_app.instance_path, file_path)

    # Security check: ensure the resolved path is within the intended subdirectories
    instance_uploads = os.path.abspath(os.path.join(current_app.instance_path, 'uploads'))
    instance_thumbs = os.path.abspath(os.path.join(current_app.instance_path, 'thumbs'))
    resolved_path = os.path.abspath(full_path)

    if not (resolved_path.startswith(instance_uploads) or resolved_path.startswith(instance_thumbs)):
        # If the path tries to escape our secure folders, forbid access
        return abort(403)

    if not os.path.isfile(resolved_path):
        return abort(404)

    # Safely serve the file from the verified directory and filename
    return send_from_directory(
        os.path.dirname(resolved_path),
        os.path.basename(resolved_path)
    )