from db.models.department import Department
from db.repositories.base import BaseRepository


class DepartmentRepository(BaseRepository[Department]):
    model = Department
