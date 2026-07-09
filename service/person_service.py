from __future__ import annotations

from typing import Dict, List, Optional

from util.io_tools import load_personnel, save_personnel


class PersonService:
    """体育馆人员档案管理服务。"""

    def __init__(self) -> None:
        self.data = load_personnel()

    def list_persons(self) -> List[Dict[str, str]]:
        return list(self.data.get("persons", []))

    def find_person(self, person_id: str) -> Optional[Dict[str, str]]:
        person_id = person_id.strip()
        for person in self.list_persons():
            if person.get("person_id") == person_id:
                return person
        return None

    def add_or_update(
        self,
        person_id: str,
        name: str,
        phone: str = "",
        remark: str = "",
    ) -> Dict[str, str]:
        person_id = person_id.strip()
        if not person_id:
            raise ValueError("人员编号不能为空。")

        person = {
            "person_id": person_id,
            "name": (name or person_id).strip(),
            "phone": phone.strip(),
            "remark": remark.strip(),
        }
        persons = self.list_persons()
        for index, old_person in enumerate(persons):
            if old_person.get("person_id") == person_id:
                persons[index] = person
                self.data["persons"] = persons
                save_personnel(self.data)
                return person

        persons.append(person)
        self.data["persons"] = persons
        save_personnel(self.data)
        return person
