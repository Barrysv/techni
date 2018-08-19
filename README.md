# Home Assistant Technicolor modem (TG-789 etc) sensor
Integration of the tgiistats script by Matt Johnston as a home assistant sensor

How to use:
1. copy to ~homeassistant/.homeassistant/custom_components/sensor/ (create this subfolder)
2. as your homeassistant user and python profile active install dependancies
ie do this: sudo su -s /bin/bash homeassistant
and: source /srv/homeassistant/bin/activate
```
  pip3 install bs4
  pip3 install requests
  pip3 install srp
```

3. in your sensors.yaml file include the following.
```
- platform: technicolor
  name: modem
  host: 10.1.1.1
  username: !secret modem_username
  password: !secret modem_password

- platform: template
  sensors:
#add to the below to match the attributes above
    up_rate:
      friendly_name: 'Up rate'
      unit_of_measurement: 'kbps'
      value_template: '{{ states.sensor.modem.attributes.up_rate }}'
    down_rate:
      friendly_name: 'Down rate'
      unit_of_measurement: 'kbps'
      value_template: '{{ states.sensor.modem.attributes.down_rate }}'
    dsl_uptime:
      friendly_name: 'DSL uptime'
      unit_of_measurement: 'time'
      value_template: '{{ states.sensor.modem.attributes.dsl_uptime}}'
    dsl_up_noisemargin:
      friendly_name: 'DSL up noisemargin'
      unit_of_measurement: 'dB'
      value_template: '{{ states.sensor.modem.attributes.up_noisemargin}}'
    dsl_down_noisemargin:
      friendly_name: 'DSL down noisemargin'
      unit_of_measurement: 'dB'
      value_template: '{{ states.sensor.modem.attributes.down_noisemargin}}'
    max_up_rate:
      friendly_name: 'DSL max up rate'
      unit_of_measurement: 'kbps'
      value_template: '{{ states.sensor.modem.attributes.up_maxrate }}'
    max_down_rate:
      friendly_name: 'DSL max down rate'
      unit_of_measurement: 'kbps'
      value_template: '{{ states.sensor.modem.attributes.down_maxrate }}'

```

4. Use Groups to customise these into a card - in my groups.yaml:
```
system_status:
  name: System
  entities:
    - sensor.modem
    - sensor.dsl_uptime
    - sensor.down_rate
    - sensor.up_rate
    - sensor.dsl_down_noisemargin
    - sensor.dsl_up_noisemargin
    - sensor.max_down_rate
    - sensor.max_up_rate
```
