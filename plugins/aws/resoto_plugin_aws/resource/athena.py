from typing import ClassVar, Dict, Optional, List

from attrs import define

from resoto_plugin_aws.resource.base import AwsResource, GraphBuilder, AwsApiSpec
from resotolib.json_bender import Bender, S, Bend, bend
from resotolib.types import Json
from resoto_plugin_aws.aws_client import AwsClient
from resoto_plugin_aws.utils import ToDict
from typing import Type, cast
import concurrent.futures


@define(eq=False, slots=False)
class AwsAthenaEncryptionConfiguration:
    kind: ClassVar[str] = "aws_athena_encryption_configuration"
    mapping: ClassVar[Dict[str, Bender]] = {"encryption_option": S("EncryptionOption"), "kms_key": S("KmsKey")}
    encryption_option: Optional[str] = None
    kms_key: Optional[str] = None


@define(eq=False, slots=False)
class AwsAthenaResultConfiguration:
    kind: ClassVar[str] = "aws_athena_result_configuration"
    mapping: ClassVar[Dict[str, Bender]] = {
        "output_location": S("OutputLocation"),
        "encryption_configuration": S("EncryptionConfiguration") >> Bend(AwsAthenaEncryptionConfiguration.mapping),
        "expected_bucket_owner": S("ExpectedBucketOwner"),
    }
    output_location: Optional[str] = None
    encryption_configuration: Optional[AwsAthenaEncryptionConfiguration] = None
    expected_bucket_owner: Optional[str] = None


@define(eq=False, slots=False)
class AwsAthenaEngineVersion:
    kind: ClassVar[str] = "aws_athena_engine_version"
    mapping: ClassVar[Dict[str, Bender]] = {
        "selected_engine_version": S("SelectedEngineVersion"),
        "effective_engine_version": S("EffectiveEngineVersion"),
    }
    selected_engine_version: Optional[str] = None
    effective_engine_version: Optional[str] = None


@define(eq=False, slots=False)
class AwsAthenaWorkGroupConfiguration:
    kind: ClassVar[str] = "aws_athena_work_group_configuration"
    mapping: ClassVar[Dict[str, Bender]] = {
        "result_configuration": S("ResultConfiguration") >> Bend(AwsAthenaResultConfiguration.mapping),
        "enforce_work_group_configuration": S("EnforceWorkGroupConfiguration"),
        "publish_cloud_watch_metrics_enabled": S("PublishCloudWatchMetricsEnabled"),
        "bytes_scanned_cutoff_per_query": S("BytesScannedCutoffPerQuery"),
        "requester_pays_enabled": S("RequesterPaysEnabled"),
        "engine_version": S("EngineVersion") >> Bend(AwsAthenaEngineVersion.mapping),
    }
    result_configuration: Optional[AwsAthenaResultConfiguration] = None
    enforce_work_group_configuration: Optional[bool] = None
    publish_cloud_watch_metrics_enabled: Optional[bool] = None
    bytes_scanned_cutoff_per_query: Optional[int] = None
    requester_pays_enabled: Optional[bool] = None
    engine_version: Optional[AwsAthenaEngineVersion] = None


@define(eq=False, slots=False)
class AwsAthenaWorkGroup(AwsResource):
    kind: ClassVar[str] = "aws_athena_work_group"
    api_spec: ClassVar[AwsApiSpec] = AwsApiSpec("athena", "list-work-groups", "WorkGroups")
    mapping: ClassVar[Dict[str, Bender]] = {
        "id": S("Name"),
        "ctime": S("CreationTime"),
        "name": S("Name"),
        "state": S("State"),
        "configuration": S("Configuration") >> Bend(AwsAthenaWorkGroupConfiguration.mapping),
        "description": S("Description"),
    }
    state: Optional[str] = None
    configuration: Optional[AwsAthenaWorkGroupConfiguration] = None
    description: Optional[str] = None

    def _arn(self) -> str:
        return f"arn:aws:athena:{self.region().id}:{self.account().id}:workgroup/{self.name}"

    @classmethod
    def collect(cls: Type[AwsResource], json: List[Json], builder: GraphBuilder) -> None:
        def fetch_workgroup(name: str) -> Optional[AwsAthenaWorkGroup]:
            result = builder.client.get(
                service="athena", action="get-work-group", result_name="WorkGroup", WorkGroup=name
            )
            if result is None:
                return None

            return cast(AwsAthenaWorkGroup, cls.from_api(result))

        def add_tags(data_catalog: AwsAthenaWorkGroup) -> None:
            tags = builder.client.list(
                "athena",
                "list_tags_for_resource",
                None,
                ResourceARN=data_catalog._arn(),
            )
            if tags:
                data_catalog.tags = bend(S("Tags", default=[]) >> ToDict(), tags[0])

        workgroups = [
            builder.submit_work(fetch_workgroup, workgroup.get("Name")) for workgroup in json if workgroup.get("Name")
        ]

        for wgf in concurrent.futures.as_completed(workgroups):
            wg = wgf.result()
            if wg is not None:
                builder.add_node(wg)
                builder.submit_work(add_tags, wg)

    def update_resource_tag(self, client: AwsClient, key: str, value: str) -> bool:
        client.call(
            service=self.api_spec.service,
            action="tag_resource",
            result_name=None,
            ResourceARN=self._arn(),
            Tags=[{"Key": key, "Value": value}],
        )
        return True

    def delete_resource_tag(self, client: AwsClient, key: str) -> bool:
        client.call(
            service=self.api_spec.service,
            action="untag_resource",
            result_name=None,
            ResourceARN=self._arn(),
            TagKeys=[key],
        )
        return True

    def delete_resource(self, client: AwsClient) -> bool:
        client.call(
            service=self.api_spec.service,
            action="delete-work-group",
            result_name=None,
            WorkGroup=self.name,
            RecursiveDeleteOption=True,
        )
        return True


@define(eq=False, slots=False)
class AwsAthenaDataCatalog(AwsResource):
    kind: ClassVar[str] = "aws_athena_data_catalog"
    api_spec: ClassVar[AwsApiSpec] = AwsApiSpec("athena", "list-data-catalogs", "DataCatalogsSummary")
    mapping: ClassVar[Dict[str, Bender]] = {
        "id": S("Name"),
        "name": S("Name"),
        "description": S("Description"),
        "type": S("Type"),
        "parameters": S("Parameters"),
    }
    description: Optional[str] = None
    type: Optional[str] = None
    parameters: Optional[Dict[str, str]] = None

    def _arn(self) -> str:
        return f"arn:aws:athena:{self.region().id}:{self.account().id}:datacatalog/{self.name}"

    @classmethod
    def collect(cls: Type[AwsResource], json: List[Json], builder: GraphBuilder) -> None:
        def fetch_data_catalog(data_catalog_name: str) -> Optional[AwsAthenaDataCatalog]:
            result = builder.client.get(
                service="athena",
                action="get-data-catalog",
                result_name="DataCatalog",
                Name=data_catalog_name,
            )
            if result is None:
                return None
            return cast(AwsAthenaDataCatalog, cls.from_api(result))

        def add_tags(data_catalog: AwsAthenaDataCatalog) -> None:
            tags = builder.client.list(
                "athena",
                "list-tags-for-resource",
                None,
                ResourceARN=data_catalog._arn(),
            )
            if tags:
                data_catalog.tags = bend(S("Tags", default=[]) >> ToDict(), tags[0])

        data_catalogs = [
            builder.submit_work(fetch_data_catalog, data_catalog.get("CatalogName"))
            for data_catalog in json
            if data_catalog.get("CatalogName")
        ]

        for catalog_future in concurrent.futures.as_completed(data_catalogs):
            catalog = catalog_future.result()
            if catalog is not None:
                builder.add_node(catalog)
                builder.submit_work(add_tags, catalog)

    def update_resource_tag(self, client: AwsClient, key: str, value: str) -> bool:
        client.call(
            service=self.api_spec.service,
            action="tag_resource",
            result_name=None,
            ResourceARN=self._arn(),
            Tags=[{"Key": key, "Value": value}],
        )
        return True

    def delete_resource_tag(self, client: AwsClient, key: str) -> bool:
        client.call(
            service=self.api_spec.service,
            action="untag_resource",
            result_name=None,
            ResourceARN=self._arn(),
            TagKeys=[key],
        )
        return True

    def delete_resource(self, client: AwsClient) -> bool:
        client.call(service="athena", action="delete-data-catalog", result_name=None, Name=self.name)
        return True


resources: List[Type[AwsResource]] = [
    AwsAthenaWorkGroup,
    AwsAthenaDataCatalog,
]
