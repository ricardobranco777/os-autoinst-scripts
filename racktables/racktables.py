# Copyright SUSE LLC
from __future__ import annotations

import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from requests.auth import HTTPBasicAuth


class Racktables:
    def __init__(self, url: str, username: str, password: str) -> None:
        self.s = requests.Session()
        self.s.verify = "/etc/ssl/certs/SUSE_Trust_Root.pem"
        self.s.auth = HTTPBasicAuth(username, password)
        self.url = url

    def search(self, search_payload: dict | None = None) -> list:
        if search_payload is None:
            search_payload = {}
        params = "&".join(f"{k}={v}" for k, v in search_payload.items())
        req = self.s.get(Path(self.url).joinpath("index.php"), params=params)
        status = req.status_code
        if status == 401:
            error_msg = "Racktables returned 401 Unauthorized. Are your credentials correct?"
            raise requests.HTTPError(error_msg)
        if status >= 300:
            error_msg = (
                f"Racktables returned statuscode {status} while trying to access {req.request.url}. "
                "Manual investigation needed."
            )
            raise requests.HTTPError(error_msg)
        soup = BeautifulSoup(req.text, "html.parser")
        result_table = soup.find("table", {"class": "cooltable"})
        return result_table.find_all(
            "tr", lambda tag: tag is not None
        )  # Racktables does not use table-heads so we have to filter the header out (it has absolutely no attributes)


class RacktablesObject:
    def __init__(self, rt_obj: Racktables) -> None:
        self.rt_obj = rt_obj

    def from_path(self, url_path: str) -> None:
        req = self.rt_obj.s.get(Path(self.rt_obj.url).joinpath(url_path))
        soup = BeautifulSoup(req.text, "html.parser")
        objectview_table = soup.find("table", {"class": "objectview"})
        portlets = list(objectview_table.find_all("div", {"class": "portlet"}))
        summary = next(filter(lambda x: x.find("h2").text == "summary", portlets))
        rows = list(summary.find_all("tr"))
        for row in rows:
            name_element = row.find("th")
            value_element = row.find("td")
            if name_element and value_element:
                name = name_element.text
                value = value_element.text
                sane_name = re.sub(r"[^a-z_]+", "", name.lower().replace(" ", "_"))
                setattr(self, sane_name, value)
