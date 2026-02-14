from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

# This looks for the "Authorization: Bearer <TOKEN>" header
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login", auto_error=False)


async def get_current_user(request: Request, token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
    )

    # 1. LOGIC FOR REACT (Tokens)
    # If the token exists in the header, validate it
    if token:
        try:
            payload = jwt.decode(token, "YOUR_SECRET_KEY", algorithms=["HS256"])
            user_id = payload.get("sub")
            if user_id:
                return user_id  # Or fetch user from DB
        except JWTError:
            raise credentials_exception

    # 2. LOGIC FOR JINJA (Cookies)
    # If no token in header, check if there is a cookie (for your current Jinja setup)
    token_cookie = request.cookies.get("access_token")
    if token_cookie:
        # Validate cookie logic here...
        return "user_from_cookie"

    # 3. IF NEITHER: Redirect or Error
    # For Jinja/Web:
    from fastapi.responses import RedirectResponse

    # If it's a browser request, redirect to login page
    if "text/html" in request.headers.get("Accept", ""):
        raise HTTPException(status_code=303, headers={"Location": "/login"})

    # For API/React:
    raise credentials_exception
