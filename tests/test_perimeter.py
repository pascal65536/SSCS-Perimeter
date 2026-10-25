from perimeter import BuildResult, PerimeterBuilder, merge_results
from perimeter.http import HttpError
from perimeter.lockfile import read_lockfile


class FakeDepsDev:
    def dependencies(self, name, version):
        return {
            "nodes": [
                {"versionKey": {"system": "PYPI", "name": name, "version": version}},
                {"versionKey": {"system": "PYPI", "name": "urllib3", "version": "2.2.2"}},
                {"versionKey": {"system": "PYPI", "name": "certifi", "version": "2024.7.4"}},
            ],
            "edges": [{"fromNode": 0, "toNode": 1}, {"fromNode": 1, "toNode": 2}],
        }


class FakePyPI:
    def package(self, name):
        return {
            "info": {
                "name": name,
                "version": "1.0",
                "summary": f"Summary {name}",
                "project_urls": {"Source": f"https://github.com/example/{name}.git"},
            },
            "releases": {"1.0": [{"upload_time": "2024-01-01T00:00:00Z"}]},
        }


def test_graph_levels_edges_and_metadata_are_deterministic():
    builder = PerimeterBuilder(FakeDepsDev(), FakePyPI(), max_workers=2)
    first = builder.build([{"name": "Requests", "version": "2.32.3"}], project_name="app")
    second = builder.build([{"name": "requests", "version": "2.32.3"}], project_name="app")
    assert first.packages == second.packages
    assert [p["level"] for p in first.packages] == ["INDIRECT", "SELF", "DIRECT"]
    requests = next(p for p in first.packages if p["name"] == "requests")
    assert requests["dependencies"] == ["urllib3"]
    assert requests["repo"] == "example/requests"
    assert requests["perimeter_root"] == ["app"]


def test_missing_depsdev_skips_root_with_warning():
    class Missing:
        def dependencies(self, name, version):
            raise HttpError(404, "test", "missing")

    result = PerimeterBuilder(Missing(), FakePyPI()).build([{"name": "gone", "version": "1"}])
    assert result.packages == []
    assert "deps.dev" in result.warnings[0]


def test_requirements_lockfile(tmp_path):
    path = tmp_path / "requirements.txt"
    path.write_text("# comment\nRequests==2.32.3\nflask[async]==3.0.3; python_version>'3.11'\n", encoding="utf-8")
    assert read_lockfile(path) == [
        {"name": "flask", "version": "3.0.3"},
        {"name": "requests", "version": "2.32.3"},
    ]


def test_union_multiple_projects_preserves_all_perimeter_roots():
    a = BuildResult([{"name": "shared", "version": "1", "level": "INDIRECT", "dependencies": [], "perimeter_root": ["a"], "repo": None}])
    b = BuildResult([{"name": "shared", "version": "2", "level": "SELF", "dependencies": [], "perimeter_root": ["b"], "repo": None}])
    merged = merge_results([a, b]).packages
    assert merged[0]["perimeter_root"] == ["a", "b"]
    assert merged[0]["level"] == "SELF" and merged[0]["version"] == "2"
