import unittest
from app.routers.vehicles import VehiclePayload, _payload_to_db, _vehicle_response, _has_vehicle_identity


class VehicleContractTests(unittest.TestCase):
    def test_legacy_form_maps_only_to_existing_v2_columns(self):
        payload = VehiclePayload(brand='Nissan', model='X-Trail', engine='SR20VET', drive='4WD', fuel='Petrol', year='2003', mileage='185000 km', vin='PNT30-123456', country='', city='', notes='')
        row = _payload_to_db(payload)
        self.assertTrue(_has_vehicle_identity(payload))
        self.assertEqual(row['make'], 'Nissan')
        self.assertEqual(row['engine_code'], 'SR20VET')
        self.assertEqual(row['drivetrain'], '4WD')
        self.assertEqual(row['fuel_type'], 'Petrol')
        self.assertEqual(row['mileage'], 185000)
        self.assertEqual(row['year'], 2003)
        self.assertEqual(row['chassis_number'], 'PNT30-123456')
        self.assertIsNone(row['vin'])
        self.assertFalse(set(row) & {'brand','engine','fuel','drive','country','city','notes','displacement'})

    def test_canonical_identity_and_compatibility_response(self):
        payload = VehiclePayload(make='Toyota', model='Crown', engine_code='1G-GZE', drivetrain='RWD', fuel_type='Petrol', mileage=0, mileage_unit='km', vin='JT123456789012345')
        row = _payload_to_db(payload)
        row['id'] = '11111111-1111-4111-8111-111111111111'
        response = _vehicle_response(row)
        self.assertEqual(response['brand'], 'Toyota')
        self.assertEqual(response['engine'], '1G-GZE')
        self.assertEqual(response['drive'], 'RWD')
        self.assertEqual(response['mileage'], 0)
        self.assertEqual(response['id'], row['id'])

    def test_only_identity_is_required(self):
        self.assertTrue(_has_vehicle_identity(VehiclePayload(brand='Toyota', model='Crown')))
        self.assertFalse(_has_vehicle_identity(VehiclePayload(model='Crown')))
        self.assertFalse(_has_vehicle_identity(VehiclePayload(brand='Toyota', model='  ')))


if __name__ == '__main__':
    unittest.main()
