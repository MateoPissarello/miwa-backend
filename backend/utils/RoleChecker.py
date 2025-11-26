from fastapi import Depends, HTTPException, status
from utils.get_current_user_cognito import TokenData, get_current_user


class RoleChecker:
    """
    Role checker that validates user roles from Cognito groups.
    
    In Cognito, roles are typically stored as groups. The user's groups
    are included in the JWT token and can be accessed via the TokenData.
    
    If you need to check specific Cognito groups, you should add a 'groups'
    field to TokenData and extract it from the JWT token claims.
    """
    def __init__(self, allowed_roles: list[str]):
        self.allowed_roles = set(allowed_roles)

    def __call__(
        self,
        current_user: TokenData = Depends(get_current_user),
    ):
        if current_user.email is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Authenticated user email claim is required",
            )

        # TODO: Implement role checking using Cognito groups
        # For now, we allow all authenticated users
        # To properly implement this, you need to:
        # 1. Add groups to TokenData in get_current_user_cognito.py
        # 2. Extract 'cognito:groups' from the JWT token
        # 3. Check if any of the user's groups match allowed_roles
        
        # Example implementation:
        # user_groups = getattr(current_user, 'groups', [])
        # if not any(group in self.allowed_roles for group in user_groups):
        #     raise HTTPException(
        #         status_code=status.HTTP_403_FORBIDDEN,
        #         detail="Operation not permitted",
        #     )
        
        # For now, just verify the user is authenticated
        pass
