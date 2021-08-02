
# full license information.
set -e
script_dir=$(cd "$(dirname "$0")" && pwd)

##############
# set defaults
##############
location=westus2
subscription_name=$(az account show --query "name" -o tsv)
user_principal_id=$(az ad signed-in-user show --query "objectId" -o tsv)
show_output=true

###########
# functions
###########

# output to stderr if output is enabled
function echo_detail {
    # The `>&2` prefix redirects the echos to stderr
    # https://clig.dev/?#the-basics
    if $show_output; then 
        >&2 echo "$@"
    fi
}

function usage {
    # don't use echo_detail because we want this, even if the user passed -q
    >&2 echo
    >&2 echo "usage: $0 [flags] \<prefix\>"
    >&2 echo
    >&2 echo flags:
    >&2 echo '--no-output, -q            no human-readable output'
    >&2 echo '--location, -l <location>  deploy to specific azure region'
    >&2 echo
}

##############
# process args
##############
while [ "$1" != "" ]; do
    case $1 in
        -h | --help)
            usage
            exit 0
            ;;

        -q | --no-output)
            show_output=false
            shift
            ;;

        --location | -l)
            location=$2
            shift; shift
            ;;

        *)
            if [ "$prefix" == "" ]; then
                prefix=$1
                shift
            else
                >&2 echo UNEXPECTED ARG: $1
                usage
                exit 1
            fi
            ;;
    esac
done

###############
# validate args
###############
if [ "$prefix" == "" ]; then
    >&2 echo EXPECTED prefix is missing
    usage
    exit 1
fi

#############################
# set variables based on args
#############################
resource_group=${prefix}_thief_rg

# warn the user

if $show_output; then
    echo_detail 
    echo_detail WARNING WARNING WARNING
    echo_detail 
    echo_detail This script is going to deploy Azure resources into the following subscription:
    echo_detail \* ${subscription_name}
    echo_detail
    echo_detail In the follwing region:
    echo_detail \* ${location}
    echo_detail 
    echo_detail Under the following resource groups:
    echo_detail \* ${resource_group}
    echo_detail
    echo_detail "(Use 'az account list' and 'az account set' to change the subscription.)"
    echo_detail
    >&2 read -p 'Press [Enter] to continue or ctrl-c to break'
fi

##################
# build thief.json
##################
# this is here as a convenience for people editing thief.bicep.  If bicep isn't installed, then
# thief.bicep probably didn't change, so we can skip this.
bicep_installed=false
which bicep > /dev/null && bicep_installed=true
if ${bicep_installed}; then
    $show_output && echo_detail "Building thief.json"
    bicep build thief.bicep
fi

########################
# create resource groups
########################
echo_detail "Creating ${resource_group}"
az group create \
    -n ${resource_group} \
    --location ${location} \
> /dev/null

##################
# deploy resources
##################
# TODO: use bicep parameter that reads the keyvault instead of passing the value as a parameter.
# This is blocked by https://github.com/Azure/bicep/issues/1028
deployment_name=thief-${RANDOM}
echo_detail "Running deployment ${deployment_name} on ${resource_group}"
outputs=$(az deployment group create \
    -f ${script_dir}/thief.json \
    -g ${resource_group} \
    --name ${deployment_name} \
    --query properties.outputs \
    --parameters \
        location=${location} \
        prefix=${prefix} \
        user_principal_id=${user_principal_id} \
        app_insights_instrumentation_key=${APP_INSIGHTS_INSTRUMENTATION_KEY} \
        shared_subscription_id=${SHARED_SUBSCRIPTION_ID} \
        shared_keyvault_name=${SHARED_KEYVAULT_NAME} \
        shared_resource_group=${SHARED_RESOURCE_GROUP} \
    )

####################################
# capture output for post-processing
####################################
enrollment_id=${prefix}-thief-enrollment
subscription_id=$(echo ${outputs} | jq -r .subscription_id.value)
iothub_name=$(echo ${outputs} | jq -r .iothub_name.value)
dps_instance_name=$(echo ${outputs} | jq -r .dps_instance_name.value)
keyvault_name=$(echo ${outputs} | jq -r .keyvault_name.value)

###################
# create DPS groups
###################
echo_detail Creating symmetric key deployment group
# OK for this to fail in case the enrollment group already exists
az iot dps enrollment-group create \
    --resource-group ${resource_group} \
    --subscription ${subscription_id} \
    --iot-hub-host-name ${iothub_name}.azure-devices.net \
    --dps-name ${dps_instance_name} \
    --enrollment-id ${enrollment_id} > /dev/null || echo 

echo_detail Fetching deployment group key
device_group_symmetric_key="$(\
    az iot dps enrollment-group show \
        --resource-group ${resource_group} \
        --subscription ${subscription_id} \
        --dps-name ${dps_instance_name} \
        --enrollment-id ${enrollment_id} \
        --show-keys \
        -o tsv \
        --query attestation.symmetricKey.primaryKey \
    )" > /dev/null

echo_detail Saving deployment group key to keyvault
az keyvault secret set \
    --subscription ${subscription_id} \
    --vault-name ${keyvault_name} \
    --name DEVICE-GROUP-SYMMETRIC-KEY \
    --value "${device_group_symmetric_key}" > /dev/null

################
#success message
################
echo_detail Deployment ${deployment_name} success
echo_detail To load variables into _thief_secrets.json, run
echo \"${script_dir}/../scripts/secrets-to-json.sh ${subscription_id} ${keyvault_name}\"


