from rest_framework.permissions import BasePermission

def has_role(*roles):
    """Build a permission class that admits only the given roles."""
    allowed=set(roles)
    class RolePermission(BasePermission):
        def has_permission(self,request,view):
            return bool(request.user and request.user.is_authenticated and request.user.role in allowed)
    RolePermission.__name__='Role_'+'_'.join(sorted(allowed))
    return RolePermission

class IsAdmin(BasePermission):
    def has_permission(self,request,view): return bool(request.user and request.user.is_authenticated and request.user.role=='ADMIN')
class IsAdminOrDoctor(BasePermission):
    def has_permission(self,request,view): return bool(request.user and request.user.is_authenticated and request.user.role in {'ADMIN','DOCTOR'})
class IsStaff(BasePermission):
    def has_permission(self,request,view): return bool(request.user and request.user.is_authenticated and request.user.role in {'ADMIN','DOCTOR','RECEPTIONIST'})
class IsAdminOrReceptionist(BasePermission):
    def has_permission(self,request,view): return bool(request.user and request.user.is_authenticated and request.user.role in {'ADMIN','RECEPTIONIST'})

IsSuperAdmin=has_role('SUPER_ADMIN')
IsPharmacyStaff=has_role('ADMIN','PHARMACIST')
IsFinanceStaff=has_role('ADMIN','ACCOUNTANT','RECEPTIONIST')
IsNursingStaff=has_role('ADMIN','NURSE','DOCTOR')
